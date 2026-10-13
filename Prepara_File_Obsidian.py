from pathlib import Path

from app import resolve_txt_filenames


def crea_indice_obsidian(file_indice_sorgente, file_output_obsidian, include_extension=False):
    path_sorgente = Path(file_indice_sorgente)
    path_output = Path(file_output_obsidian)

    if not path_sorgente.exists():
        print(f"Errore: Il file {file_indice_sorgente} non esiste.")
        return

    try:
        contenuto = path_sorgente.read_text(encoding="utf-8-sig")
        files_txt, indici_mancanti = resolve_txt_filenames(contenuto, path_sorgente.parent)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Errore durante la lettura dell'indice: {error}")
        return

    if indici_mancanti:
        print("File .txt non trovati per gli indici: " + ", ".join(indici_mancanti))
        return
    if not files_txt:
        print("Nessun file .txt trovato nell'indice sorgente.")
        return

    righe_nuovo_indice = [
        "# Indice dei Contenuti",
        "",
        "Ecco la lista dei file collegati per Obsidian:",
        "",
    ]
    for file_txt in files_txt:
        nome_nota = file_txt if include_extension else Path(file_txt).stem
        riga_link = f"- [[{nome_nota}]]"
        righe_nuovo_indice.append(riga_link)

    try:
        path_output.write_text("\n".join(righe_nuovo_indice) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"Errore durante il salvataggio: {error}")
        return
    print(f"Successo! Creato il file '{file_output_obsidian}' con {len(files_txt)} collegamenti.")


# Configurazione dei nomi dei file
FILE_SORGENTE = "indice.md"
FILE_OUTPUT = "lista_obsidian.md"

if __name__ == "__main__":
    crea_indice_obsidian(FILE_SORGENTE, FILE_OUTPUT)