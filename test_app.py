import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import app
from app import AI_TEXT_OVERLAP_CHARS, MAX_AI_TEXT_CHARS, add_contextual_role_tags, analyze_text_with_ollama, build_obsidian_markdown, build_obsidian_note_markdown, extract_json_object, extract_txt_filenames, format_entity_tags, is_valid_ai_tag, keep_explicit_political_tags, remove_partial_person_tags, resolve_txt_filenames, split_ai_text
from Prepara_File_Obsidian import crea_indice_obsidian


class SourceFolderApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source"
        self.output = self.root / "output"
        self.source.mkdir()
        self.output.mkdir()
        (self.source / "B.txt").write_text("Testo completo B.\n", encoding="utf-8")
        (self.source / "a.TXT").write_text("Testo completo A.\n", encoding="utf-8")
        (self.source / "ignora.md").touch()
        (self.source / "nested").mkdir()
        (self.source / "nested" / "escluso.txt").touch()
        (self.source / "directory.txt").mkdir()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, endpoint, fields):
        boundary = "txttoobsidian-test"
        chunks = []
        for name, value in fields.items():
            disposition = f'Content-Disposition: form-data; name="{name}"'
            if name == "markdown":
                disposition += '; filename="indice.md"'
            chunks.append(
                f"--{boundary}\r\n{disposition}\r\n\r\n{value}\r\n".encode("utf-8")
            )
        chunks.append(f"--{boundary}--\r\n".encode())
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            connection.request("POST", endpoint, body=b"".join(chunks), headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-App-Token": app.TOKEN,
            })
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_previews_directory_without_index_and_excludes_subfolders(self):
        status, data = self.post("/api/preview", {"source_directory": str(self.source)})
        self.assertEqual(status, 200)
        self.assertEqual(data["filenames"], ["a.TXT", "B.txt"])
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["missing_indexes"], [])

    def test_previews_browser_selection_without_index(self):
        status, data = self.post("/api/preview", {
            "source_filenames": json.dumps(["B.txt", "a.TXT"]),
            "include_extension": "true",
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["filenames"], ["a.TXT", "B.txt"])
        self.assertTrue(data["include_extension"])

    def test_reports_missing_empty_invalid_and_ambiguous_sources(self):
        empty = self.root / "empty"
        empty.mkdir()
        cases = [
            ({}, "Seleziona la cartella"),
            ({"source_filenames": "[]"}, "Seleziona la cartella"),
            ({"source_directory": str(empty)}, "non contiene file .txt"),
            ({"source_directory": str(self.root / "missing")}, "non esiste"),
            ({"source_filenames": '["../B.txt"]'}, "nomi file non validi"),
            ({"source_filenames": '["B.txt", "b.TXT"]'}, "duplicati"),
        ]
        for fields, message in cases:
            with self.subTest(fields=fields):
                status, data = self.post("/api/preview", fields)
                self.assertEqual(status, 400)
                self.assertIn(message, data["error"])

    def test_index_still_limits_files_and_empty_index_does_not_list_folder(self):
        for markdown, expected in [("- B.txt", ["B.txt"]), ("# Nessun riferimento", [])]:
            with self.subTest(markdown=markdown):
                status, data = self.post("/api/preview", {
                    "markdown": markdown, "source_directory": str(self.source),
                })
                self.assertEqual(status, 200)
                self.assertEqual(data["filenames"], expected)

    def test_generates_without_index_and_preserves_overwrite_protection(self):
        fields = {"source_directory": str(self.source), "output_directory": str(self.output)}
        status, data = self.post("/api/generate", fields)
        self.assertEqual(status, 200)
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["created_notes"], [])
        target = self.output / "lista_obsidian.md"
        self.assertEqual(target.read_text(encoding="utf-8"), "# Indice Obsidian\n\n- [[a]]\n- [[B]]\n")
        status, data = self.post("/api/generate", fields)
        self.assertEqual(status, 400)
        self.assertIn("Esistono già file", data["error"])

    def test_without_index_creates_tagged_note_only_for_selected_file(self):
        for use_browser in (False, True):
            with self.subTest(use_browser=use_browser):
                job_id = ("b" if use_browser else "a") * 32
                self.addCleanup(app._clear_ai_text_cache, job_id)
                source_fields = (
                    {"source_filenames": '["B.txt", "a.TXT"]'} if use_browser
                    else {"source_directory": str(self.source)}
                )
                analysis_fields = {"filename": "B.txt", "model": "test-model", "job_id": job_id}
                if use_browser:
                    analysis_fields["file_text"] = "Testo completo B.\n"
                else:
                    analysis_fields.update(source_fields)
                with patch("app.analyze_text_with_ollama", return_value=["#persona/Mario_Rossi"]):
                    status, data = self.post("/api/analyze", analysis_fields)
                self.assertEqual(status, 200)
                status, data = self.post("/api/generate", {
                    **source_fields, "output_directory": str(self.output), "overwrite": "true",
                    "job_id": job_id, "ai_filenames": '["B.txt"]',
                    "tags_by_filename": '{"B.txt": ["#persona/Mario_Rossi"]}',
                })
                self.assertEqual(status, 200)
                self.assertEqual(data["created_notes"], ["B.md"])
                note = (self.output / "B.md").read_text(encoding="utf-8")
                self.assertIn("Testo completo B.\n", note)
                self.assertIn("Tags: #persona/Mario_Rossi", note)
                self.assertFalse((self.output / "a.md").exists())
                self.assertEqual((self.source / "B.txt").read_text(encoding="utf-8"), "Testo completo B.\n")


class ObsidianIndexTests(unittest.TestCase):
    def test_extracts_names_with_spaces_and_special_characters(self):
        source = """# Indice
- Cartella/Analisi HR - 2026 (finale) & note.txt
- [File con apostrofo's.txt](File con apostrofo's.txt)
- guida.txt, guida.txt
- immagine.png
"""
        self.assertEqual(
            extract_txt_filenames(source),
            ["Analisi HR - 2026 (finale) & note.txt", "File con apostrofo's.txt", "guida.txt"],
        )

    def test_generates_clean_wikilinks_by_default(self):
        result = build_obsidian_markdown(["Nota speciale.txt", "Seconda-nota.txt"])
        self.assertEqual(result, "# Indice Obsidian\n\n- [[Nota speciale]]\n- [[Seconda-nota]]\n")

    def test_accepts_every_supported_ai_tag_category(self):
        tags = [
            "#persona/Antonio_Ingroia",
            "#magistrato/Paolo_Borsellino",
            "#mafioso/Gaspare_Mutolo",
            "#estrema_destra/Nome",
            "#giornalista/Nome",
            "#avvocato/Nome",
            "#data/1992-05-23",
            "#luogo/Caltanissetta",
            "#terrorismo/Brigate_Rosse",
            "#politico/Calogero_Mannino",
            "#partito/Partito_Alfa",
        ]

        self.assertTrue(all(is_valid_ai_tag(tag) for tag in tags))
        self.assertFalse(is_valid_ai_tag("#persona/Non valido!"))

    def test_can_include_extension_in_wikilinks(self):
        self.assertEqual(
            build_obsidian_markdown(["Nota.txt"], include_extension=True),
            "# Indice Obsidian\n\n- [[Nota.txt]]\n",
        )

    def test_formats_ai_entities_as_clean_obsidian_tags(self):
        tags = format_entity_tags({
            "persone": ["Giovanni Falcone", "Paolo Borsellino", "tinebra", "Gaspare Mutolo", "Leonardo Messina", "due giornalisti francesi"],
            "magistrati": ["Giovanni Falcone", "Tinebra"],
            "mafiosi": ["Gaspare Mutolo", "Leonardo Messina"],
            "giornalisti": ["Mario Giornalista"],
            "avvocati": ["Lucia Avvocata"],
            "estrema_destra": ["Carlo Estremo"],
            "date": ["23 maggio 1992", "1992"],
            "luoghi": ["Via d'Amelio", "Palermo"],
            "terroristi_organizzazioni_terroristiche": ["Brigate Rosse", "Brigate Rosse"],
            "politici": ["Mario Rossi"],
            "partiti": ["Partito Alfa!"],
        })
        self.assertEqual(tags, [
            "#persona/Giovanni_Falcone",
            "#persona/Paolo_Borsellino",
            "#persona/Tinebra",
            "#persona/Gaspare_Mutolo",
            "#persona/Leonardo_Messina",
            "#magistrato/Giovanni_Falcone",
            "#magistrato/Tinebra",
            "#mafioso/Gaspare_Mutolo",
            "#mafioso/Leonardo_Messina",
            "#estrema_destra/Carlo_Estremo",
            "#giornalista/Mario_Giornalista",
            "#avvocato/Lucia_Avvocata",
            "#data/1992-05-23",
            "#data/1992",
            "#luogo/Via_dAmelio",
            "#luogo/Palermo",
            "#terrorismo/Brigate_Rosse",
            "#politico/Mario_Rossi",
            "#partito/Partito_Alfa",
        ])
        markdown = build_obsidian_markdown(["Nota.txt"], tags_by_filename={"Nota.txt": tags})
        self.assertIn("  Tags: #persona/Giovanni_Falcone #persona/Paolo_Borsellino #persona/Tinebra", markdown)

    def test_does_not_classify_mafia_as_terrorism(self):
        tags = format_entity_tags({
            "terroristi_organizzazioni_terroristiche": ["Mafia", "La Mafia", "Cosa nostra", "Brigate Rosse"],
        })

        self.assertEqual(tags, ["#terrorismo/Brigate_Rosse"])

    def test_rejects_invalid_dates_and_single_character_entities(self):
        tags = format_entity_tags({
            "date": ["01_Ingroia", "92", "23 maggio 1992", "1992"],
            "luoghi": ["M", "Palermo"],
        })

        self.assertEqual(tags, ["#data/1992-05-23", "#data/1992", "#luogo/Palermo"])

    def test_removes_partial_person_when_full_name_is_available(self):
        tags = [
            "#persona/Giovanni", "#persona/Giovanni_Falcone", "#persona/Falcone",
            "#persona/Tinebra", "#persona/Mutolo", "#persona/Gaspare_Mutolo",
        ]

        self.assertEqual(
            remove_partial_person_tags(tags),
            ["#persona/Giovanni_Falcone", "#persona/Tinebra", "#persona/Gaspare_Mutolo"],
        )

    def test_adds_roles_from_local_judicial_and_mafia_evidence(self):
        tags = [
            "#persona/Paolo_Borsellino", "#persona/Giovanni_Falcone",
            "#persona/Gaspare_Mutolo", "#persona/Leonardo_Messina",
            "#persona/Giovanni_Brusca", "#persona/Totò_Cancemi",
            "#persona/Mario_Rossi",
        ]
        source = (
            "Il fascicolo fu assegnato ad altri magistrati, poi a Paolo Borsellino. "
            "Prima, Giovanni Falcone si occupava delle indagini presso la Procura di Palermo. "
            "I pentiti Gaspare Mutolo e Leonardo Messina parlarono dei rapporti con la mafia. "
            "I collaboratori di giustizia Giovanni Brusca e Totò Cancemi parlarono del papello. "
            "Mario Rossi collaborò con la giustizia su una frode fiscale."
        )

        inferred = add_contextual_role_tags(tags, source)

        self.assertIn("#magistrato/Paolo_Borsellino", inferred)
        self.assertIn("#magistrato/Giovanni_Falcone", inferred)
        self.assertIn("#mafioso/Gaspare_Mutolo", inferred)
        self.assertIn("#mafioso/Leonardo_Messina", inferred)
        self.assertIn("#mafioso/Giovanni_Brusca", inferred)
        self.assertIn("#mafioso/Totò_Cancemi", inferred)
        self.assertNotIn("#mafioso/Mario_Rossi", inferred)
        self.assertNotIn("#magistrato/Mario_Rossi", inferred)

    def test_adds_roles_from_ingroia_asr_transcript(self):
        source_path = next((Path(__file__).parent / "prova").glob("01_Ingroia*.md"))
        source = source_path.read_text(encoding="utf-8")
        tags = [
            "#persona/Paolo_Borsellino", "#persona/Giovanni_Falcone",
            "#persona/Gaspere_Mutolo", "#persona/Leonardo_Messina",
            "#persona/Giovanni_Brusca", "#persona/Totò_Cancemi",
        ]

        inferred = add_contextual_role_tags(tags, source)

        self.assertIn("#magistrato/Paolo_Borsellino", inferred)
        self.assertIn("#magistrato/Giovanni_Falcone", inferred)
        for person in ("Gaspere_Mutolo", "Leonardo_Messina", "Giovanni_Brusca", "Totò_Cancemi"):
            self.assertIn(f"#mafioso/{person}", inferred)
        self.assertNotIn("#magistrato/Gaspere_Mutolo", inferred)
        self.assertNotIn("#mafioso/Giovanni_Falcone", inferred)

    def test_ai_chunks_cover_full_text_without_exceeding_limit(self):
        source = "inizio " + ("trascrizione completa " * 900) + "Tinebra e Gaspare Mutolo fine"

        chunks = split_ai_text(source)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= MAX_AI_TEXT_CHARS for chunk in chunks))
        self.assertIn("Tinebra e Gaspare Mutolo fine", " ".join(chunks))
        self.assertTrue(all(
            chunks[index][-AI_TEXT_OVERLAP_CHARS:] == chunks[index + 1][:AI_TEXT_OVERLAP_CHARS]
            for index in range(len(chunks) - 1)
        ))

    def test_builds_individual_note_with_full_source_text_and_tags(self):
        source_text = "Prima riga originale.\nSeconda riga completa.\n"
        note = build_obsidian_note_markdown(
            "Trascrizione_01.txt",
            source_text,
            ["#politico/Mario_Rossi", "#partito/Partito_Alfa"],
        )

        self.assertEqual(
            note,
            "# Trascrizione_01\n\nPrima riga originale.\nSeconda riga completa.\n"
            "\nTags: #politico/Mario_Rossi #partito/Partito_Alfa\n",
        )
        self.assertIn(source_text, note)

    def test_removes_political_tags_from_people_only_identified_as_magistrates(self):
        tags = ["#politico/Giovanni_Falcone", "#politico/Paolo_Borsellino", "#terrorismo/Brigate_Rosse"]
        source = "Giovanni Falcone e Paolo Borsellino erano due magistrati."

        self.assertEqual(keep_explicit_political_tags(tags, source), ["#terrorismo/Brigate_Rosse"])

    def test_keeps_political_tag_when_elective_role_is_explicit(self):
        tags = ["#politico/Giuseppe_Conte"]
        source = "Giuseppe Conte è stato Presidente del Consiglio."

        self.assertEqual(keep_explicit_political_tags(tags, source), tags)

    def test_does_not_transfer_political_role_to_nearby_person(self):
        tags = ["#politico/Antonio_Ingroia", "#politico/Paolo_Borsellino"]
        source = "Antonio Ingroia è un politico. Ha lavorato con Paolo Borsellino, magistrato."

        self.assertEqual(keep_explicit_political_tags(tags, source), ["#politico/Antonio_Ingroia"])

    def test_keeps_local_minister_role_and_drops_borsellino_false_positive(self):
        tags = ["#politico/Calogero_Mannino", "#politico/Borsellino"]
        source = (
            "Paolo Borsellino rientra da un viaggio a Roma e incontra il ministro Andò. "
            "L'esposto parlava di un ipotetico incontro con l'allora ministro Calogero Mannino.\n"
            "Tags: #politico/Calogero_Mannino #politico/Borsellino"
        )

        self.assertEqual(keep_explicit_political_tags(tags, source), ["#politico/Calogero_Mannino"])

    def test_extracts_json_object_from_wrapped_response(self):
        content = 'Risposta:\n```json\n{"politici": ["Mario Rossi"]}\n```'

        self.assertEqual(extract_json_object(content), {"politici": ["Mario Rossi"]})

    def test_returns_none_when_response_has_no_json_object(self):
        self.assertIsNone(extract_json_object("Non riesco a restituire il risultato richiesto."))

    def test_retries_truncated_chunks_as_smaller_requests(self):
        class FakeClient:
            calls = 0

            def chat(self, **kwargs):
                self.calls += 1
                if len(kwargs["messages"][1]["content"]) > 1400:
                    return SimpleNamespace(
                        message=SimpleNamespace(content='{"persone": ['),
                        done_reason="length",
                    )
                return SimpleNamespace(
                    message=SimpleNamespace(content='{"persone": ["Mario Rossi"]}'),
                    done_reason="stop",
                )

        client = FakeClient()
        fake_ollama = SimpleNamespace(Client=lambda **kwargs: client)
        with patch.dict("sys.modules", {"ollama": fake_ollama}):
            tags = analyze_text_with_ollama("x" * 1500, "test-model")

        self.assertEqual(tags, ["#persona/Mario_Rossi"])
        self.assertEqual(client.calls, 3)

    def test_retries_timed_out_chunks_as_smaller_requests(self):
        class FakeClient:
            calls = 0

            def chat(self, **kwargs):
                self.calls += 1
                if len(kwargs["messages"][1]["content"]) > 1400:
                    raise TimeoutError("request timed out")
                return SimpleNamespace(
                    message=SimpleNamespace(content='{"persone": ["Mario Rossi"]}'),
                    done_reason="stop",
                )

        client = FakeClient()
        fake_ollama = SimpleNamespace(Client=lambda **kwargs: client)
        with patch.dict("sys.modules", {"ollama": fake_ollama}):
            tags = analyze_text_with_ollama("x" * 1500, "test-model")

        self.assertEqual(tags, ["#persona/Mario_Rossi"])
        self.assertEqual(client.calls, 3)

    def test_ignores_prose_with_a_space_before_extension(self):
        self.assertEqual(extract_txt_filenames("Seleziona un file con estensione .txt."), [])

    def test_resolves_numbered_entries_to_matching_file_prefixes(self):
        with TemporaryDirectory() as directory:
            Path(directory, "01_Ingroia_ _Indagini a Contrada su via d'Amelio. Fatto che fa rabbrividire_.txt").touch()
            Path(directory, "02_Lodato_ _Falcone vedeva Contrada come regista delle 'menti raffinatissime'_.txt").touch()
            source = "\n".join([
                "01. **[SCARICATO]** Ingroia: Indagini a Contrada su via d'Amelio. Fatto che fa rabbrividire",
                "02. **[SCARICATO]** Lodato: Falcone vedeva Contrada come regista delle 'menti raffinatissime'",
            ])

            filenames, missing = resolve_txt_filenames(source, Path(directory))

        self.assertEqual(filenames, [
            "01_Ingroia_ _Indagini a Contrada su via d'Amelio. Fatto che fa rabbrividire_.txt",
            "02_Lodato_ _Falcone vedeva Contrada come regista delle 'menti raffinatissime'_.txt",
        ])
        self.assertEqual(missing, [])

    def test_reports_numbered_entries_without_a_matching_source_file(self):
        with TemporaryDirectory() as directory:
            filenames, missing = resolve_txt_filenames("03. **[SCARICATO]** Titolo", Path(directory))

        self.assertEqual(filenames, [])
        self.assertEqual(missing, ["03"])

    def test_resolves_from_selected_filenames_and_reports_missing_indexes(self):
        source = "\n".join([
            "01. **[SCARICATO]** Primo titolo",
            "02. **[FALLITO]** Secondo titolo",
        ])

        filenames, missing = resolve_txt_filenames(source, source_filenames=["01_Primo titolo.txt"])

        self.assertEqual(filenames, ["01_Primo titolo.txt"])
        self.assertEqual(missing, ["02"])

    def test_cli_script_creates_links_from_numbered_entries(self):
        with TemporaryDirectory() as directory:
            source = Path(directory, "indice.md")
            output = Path(directory, "obsidian.md")
            Path(directory, "01_Ingroia_ _Indagini a Contrada_.txt").touch()
            source.write_text("01. **[SCARICATO]** Ingroia: Indagini a Contrada", encoding="utf-8")

            crea_indice_obsidian(source, output)

            self.assertIn("- [[01_Ingroia_ _Indagini a Contrada_]]", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
