# MTUOC_TranslationMemory
Python class and programs to manage translation memories

## MTUOC Translation Memory Management Tool Tutorial

This tutorial guides you through using both the Command Line Interface (CLI) via argparse and the Graphical User Interface (GUI) of the MTUOC Translation Memory tool. This tool handles large-scale translation memories (2.5M+ segments), features ultra-fast 100% and fuzzy matching, and supports Moses, TMX, TabTxt, and XLIFF/XLF formats.

### COMMAND LINE INTERFACE (CLI) USAGE

The CLI utilizes a sub-command structure (similar to git). The general syntax requires providing the global database path first, followed by the specific action command and its parameters.

**Global Help:**

To view all available actions and global arguments, run:

`python3 MTUOC_TranslationMemory.py --help`

**Action Help:**

To view specific parameters required for an action, append --help after the action name:

`python3 MTUOC_TranslationMemory.py --db memory.db index_tmx --help`

**Action 1: Indexing a Moses Corpus**: Use this action to import parallel corpora split into separate source and target text files.

Command:

`python3 MTUOC_TranslationMemory.py --db memory.db index_moses --src_file corpus.en --tgt_file corpus.ca --batch_size 10000`

Arguments:

* `--src_file`: Path to the source language text file.
* `--tgt_file`: Path to the target language text file.
* `--batch_size`: (Optional) Number of segments processed per atomic database transaction. Default is 10000.

**Action 2: Indexing a TMX File**: Use this action to import standard TMX translation memory files. You must specify valid language codes matching those inside the TMX.

Command:

`python3 MTUOC_TranslationMemory.py --db memory.db index_tmx --tmx_file alignment.tmx --src_langs en en-US ENG --tgt_langs ca ca-ES CAT --batch_size 5000`

Arguments:

* `--tmx_file`: Path to the TMX input file.
* `--src_langs`: Space-separated list of accepted source language codes.
* `--tgt_langs`: Space-separated list of accepted target language codes.
* `--batch_size`: (Optional) Number of units parsed before writing to the database. Default is 5000.

**Action 3: Indexing Tabulated Text (TabTxt)**: Use this action to import tab-separated (.tsv or .txt) files containing "source \t target" columns. It natively handles compressed .txt.gz files.

Command (Standard Column Order):

`python3 MTUOC_TranslationMemory.py --db memory.db index_tabtxt --tabtxt_file legal_corpus.txt.gz`

Command (Swapped Column Order):

`python3 MTUOC_TranslationMemory.py --db memory.db index_tabtxt --tabtxt_file legal_corpus.txt --reverse`

Arguments:

* `--tabtxt_file`: Path to the tabulated text file (.txt, .tsv, or .txt.gz).
* `--reverse`: (Optional flag) If set, treats the 1st column as target language and the 2nd column as source language.
* `--batch_size`: (Optional) Number of segments per batch insertion. Default is 10000.

**Action 4: Performing an Ultra-Fast Search**: Query the translation memory for matches. Asking for 100.0% similarity triggers an optimized index shortcut that skips fuzzy n-gram calculations entirely.

Fuzzy Search Example:

`python3 MTUOC_TranslationMemory.py --db memory.db search --query "We will keep your personal data." --min_similarity 75.0 --max_candidates 10`

Exact Search Example:

`python3 MTUOC_TranslationMemory.py --db memory.db search --query "In this case, they will only be kept." --min_similarity 100.0`

Arguments:

* --query: The source sentence text string to look up.
* --min_similarity: (Optional) Minimum similarity percentage threshold (0.0 to 100.0). Default is 70.0.
* --max_candidates: (Optional) Maximum number of translation suggestions to display. Default is 100.

**Action 5: Creating a Project Sub-Memory**: Extract an optimized, lightweight TMX project sub-memory from a giant database based on a reference text or translation file. It supports single-line text files (.txt) or CAT tool bilingual files (.xlf, .xliff).

From an XLIFF file:

`python3 MTUOC_TranslationMemory.py --db memory.db create_submemory --input documentation.xlf --output_tmx project_memory.tmx --min_similarity 70.0 --sl en --tl ca`

From a plain text file containing one source sentence per line:

`python3 MTUOC_TranslationMemory.py --db memory.db create_submemory --input file_of_phrases.txt --output_tmx project_memory.tmx --min_similarity 75.0 --sl en --tl ca`

Arguments:

* `--input`: Path to an XLIFF/XLF file OR a plain text file with one phrase per line.
* `--output_tmx`: Output path where the extracted TMX sub-memory will be saved.
* `--min_similarity`: Minimum similarity score required to include a segment pair in the sub-memory.
* `--sl`: Source language code metadata written to the TMX header (e.g., en).
* `--tl`: Target language code metadata written to the TMX header (e.g., ca).

## GRAPHICAL USER INTERFACE (GUI) USAGE

The GUI provides an intuitive, tabbed interface to interact with the database without writing console commands. It includes asynchronous processing so huge file indexations do not freeze the window.

### Launching the GUI:
Ensure both MTUOC_TranslationMemory.py and MTUOC_GUI.py are in the same folder. Run the following command:

`python3 MTUOC_TranslationMemoryGUI.py`

You can also use the binary file for Windows MTUOC_TranslationMemoryGUI.exe and double-clicking from the file browser.

**Step 1: Establishing a Global Database Connection**

Before running any action, you must connect to a database using the top permanent bar:

* Click the "Browse..." button next to the "Database Path" entry.
* Select an existing .db file to open it, or type a new name (e.g., new_vault.db) in the file selector window to create a fresh database.
* Click the "Connect" button.

The status label will change from "Disconnected" (Red) to "Connected" (Green) and will display the total number of segments currently stored in the memory.

<img width="1000" height="700" alt="image" src="https://github.com/user-attachments/assets/dffe0f1d-f82f-4aa7-bbf6-ccac07772336" />

**Step 2: Navigating the Action Tabs**

In the "Search" Tab:

* Type or paste your source text into the "Search Query" box.
* Adjust the "Min Similarity %" and "Max Candidates" numeric sliders.
* Click "Perform Search".

Matching segments will immediately populate the "Found Candidates" list box on the right side, showing their match percentage score next to the target text.

<img width="1000" height="700" alt="image" src="https://github.com/user-attachments/assets/6915a407-6a75-4daa-b96d-88c0b9072b7b" />


"Create SubMemory" Tab:

    In the "Input File" row, click "Select" to upload an XLIFF, XLF, or a flat TXT file containing your project source sentences.

    In the "Output TMX Save Path" row, click "Select" to define where the new TMX file should be saved.

    Set the similarity threshold and the language attributes (SL/TL) for the TMX file metadata.

    Click "Generate TMX SubMemory". The process runs in the background, filtering out duplicate matches automatically.

"Index Moses" Tab:

    Click "Browse" to choose the file containing the source language sentences.

    Click "Browse" to choose the file containing the matching target language sentences.

    Click "Start Moses Indexation".

"Index TMX" Tab:

    Click "Browse" to choose your input .tmx file.

    In the language fields, specify the exact language codes to extract, separated by spaces (e.g., "en en-US" for source, "ca ca-ES" for target).

    Click "Start TMX Indexation".

"Index TabTxt" Tab:

    Click "Browse" to select a .txt, .tsv, or compressed .txt.gz tabulated file.

    Check the "Reverse Columns" box if your file places the target language in the first column and the source language in the second column.

    Click "Start TabTxt Indexation".

Step 3: Monitoring Progress and Logs
The black console widget located at the bottom of the window ("System Logs & Progress") captures the standard Python output stream. When performing long background indexing tasks on heavy files, it will print real-time counters (e.g., "> Indexed segments: 140,000") and database compression steps (VACUUM/ANALYZE) so you can track operations exactly as they happen.
