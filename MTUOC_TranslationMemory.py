import sqlite3
import os
import re
import sys
from rapidfuzz import fuzz
import xml.etree.ElementTree as ET
import gzip
from datetime import datetime

class MTUOC_TranslationMemory:
    def __init__(self, db_path):
        """Initializes the translation memory (2.5M+ segments)."""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.vocab_cache = {}      # Cache for n-gram IDs
        self.blacklist_cache = set() # Cache for forbidden IDs (RAM)
        self._setup_db()
        self._create_schema()
        self._load_blacklist()

    def _setup_db(self):
        """Critical configuration for multi-gigabyte databases."""
        self.cursor.execute("PRAGMA journal_mode = WAL")
        self.cursor.execute("PRAGMA synchronous = NORMAL")
        # Maps the file to virtual memory (ideal for 13GB+ files)
        self.cursor.execute("PRAGMA mmap_size = 30000000000") 
        self.cursor.execute("PRAGMA cache_size = -2000000") # 2GB RAM cache
        self.cursor.execute("PRAGMA foreign_keys = ON")

    def _create_schema(self):
        """Creates the optimized inverted index structure and exact search index."""
        self.cursor.executescript('''
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY,
                source_text TEXT,
                target_text TEXT,
                source_len INTEGER
            );

            CREATE TABLE IF NOT EXISTS vocab (
                id INTEGER PRIMARY KEY,
                ngram TEXT UNIQUE
            );

            CREATE TABLE IF NOT EXISTS ngrams (
                vocab_id INTEGER,
                segment_id INTEGER,
                PRIMARY KEY (vocab_id, segment_id),
                FOREIGN KEY (vocab_id) REFERENCES vocab(id),
                FOREIGN KEY (segment_id) REFERENCES segments(id)
            ) WITHOUT ROWID;

            CREATE TABLE IF NOT EXISTS ngrams_blacklist (
                vocab_id INTEGER PRIMARY KEY,
                occurrence_count INTEGER,
                FOREIGN KEY (vocab_id) REFERENCES vocab(id)
            );

            CREATE INDEX IF NOT EXISTS idx_segments_len ON segments(source_len);
            
            -- Case-insensitive index for instant exact matches
            CREATE INDEX IF NOT EXISTS idx_segments_source ON segments(source_text COLLATE NOCASE);
        ''')
        self.conn.commit()

    def _load_blacklist(self):
        """Loads forbidden IDs into RAM for instant filtering."""
        self.cursor.execute("SELECT vocab_id FROM ngrams_blacklist")
        self.blacklist_cache = {row[0] for row in self.cursor.fetchall()}

    def _normalize(self, text):
        """Cleans tags and normalizes spaces (preserves case)."""
        if not text: return ""
        text = re.sub(r'<[^>]+>', ' ', text)
        return " ".join(text.split())

    def _get_ngrams(self, text, min_n=2, max_n=4):
        """Generates n-grams (always lowercase for searching)."""
        ngrams = set()
        text_padded = f" {text.lower()} " 
        for n in range(min_n, max_n + 1):
            for i in range(len(text_padded) - n + 1):
                ngrams.add(text_padded[i:i+n])
        return ngrams

    def _get_vocab_id(self, ngram):
        """Returns the n-gram ID if it is not blacklisted."""
        if ngram in self.vocab_cache:
            vid = self.vocab_cache[ngram]
            return vid if vid not in self.blacklist_cache else None
        
        self.cursor.execute("INSERT OR IGNORE INTO vocab (ngram) VALUES (?)", (ngram,))
        self.cursor.execute("SELECT id FROM vocab WHERE ngram = ?", (ngram,))
        res = self.cursor.fetchone()
        if not res: return None
        
        vid = res[0]
        self.vocab_cache[ngram] = vid
        return vid if vid not in self.blacklist_cache else None

    def _insert_batch(self, batch):
        """Inserts a batch of segments atomically."""
        try:
            self.cursor.execute("BEGIN TRANSACTION")
            for src, tgt in batch:
                src_clean = self._normalize(src)
                if not src_clean: continue

                self.cursor.execute(
                    "INSERT INTO segments (source_text, target_text, source_len) VALUES (?, ?, ?)",
                    (src_clean, tgt, len(src_clean))
                )
                sid = self.cursor.lastrowid
                
                ngrams = self._get_ngrams(src_clean)
                ngram_ids = []
                for ng in ngrams:
                    vid = self._get_vocab_id(ng)
                    if vid: # Automatically filters blacklisted n-grams
                        ngram_ids.append((vid, sid))
                
                if ngram_ids:
                    self.cursor.executemany(
                        "INSERT OR IGNORE INTO ngrams (vocab_id, segment_id) VALUES (?, ?)", 
                        ngram_ids
                    )
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            print(f"\n[SQL Error]: {e}")

    def prune_common_ngrams(self, threshold_percent=1.0):
        """Prunes frequent n-grams and logs them with their frequency."""
        self.cursor.execute("SELECT COUNT(*) FROM segments")
        total = self.cursor.fetchone()[0]
        if total == 0: return
        limit = int(total * (threshold_percent / 100))
        
        print(f"\n> Frequency analysis (Limit: {limit} occurrences)...")
        
        # Save to blacklist with current occurrence count
        self.cursor.execute("""
            INSERT OR REPLACE INTO ngrams_blacklist (vocab_id, occurrence_count)
            SELECT vocab_id, COUNT(segment_id) as freq
            FROM ngrams
            GROUP BY vocab_id
            HAVING freq > ?
        """, (limit,))
        
        # Remove them from the main table to boost speed and save space
        self.cursor.execute("""
            DELETE FROM ngrams 
            WHERE vocab_id IN (SELECT vocab_id FROM ngrams_blacklist)
        """)
        
        self.conn.commit()
        self._load_blacklist() # Update RAM cache
        print(f"> Blacklist updated ({len(self.blacklist_cache)} forbidden n-grams).")

    def optimize(self):
        """Compacts the file and regenerates search statistics."""
        print("> Optimizing database (VACUUM/ANALYZE)...")
        self.conn.execute("VACUUM")
        self.conn.execute("ANALYZE")
        print("> Optimization completed.")

    def index_moses(self, source_file, target_file, batch_size=10000):
        """Indexes Moses files and applies automatic pruning at the end."""
        if not os.path.exists(source_file) or not os.path.exists(target_file):
            raise FileNotFoundError("Moses file not found.")

        processed = 0
        with open(source_file, 'r', encoding='utf-8') as f_src, \
             open(target_file, 'r', encoding='utf-8') as f_tgt:
            
            while True:
                src_lines = [f_src.readline() for _ in range(batch_size)]
                tgt_lines = [f_tgt.readline() for _ in range(batch_size)]
                batch = [(s.strip(), t.strip()) for s, t in zip(src_lines, tgt_lines) if s.strip() and t.strip()]
                
                if not batch: break
                
                self._insert_batch(batch)
                processed += len(batch)
                print(f"\r> Processed segments: {processed:,}", end="", flush=True)

        print(f"\nIndexation finished. Applying improvements...")
        self.prune_common_ngrams(threshold_percent=1.0)
        self.optimize()
        
    def index_tmx(self, tmx_file, source_langs, target_langs, batch_size=5000):
        """
        Indexes a TMX file.
        source_langs: list of language codes (e.g., ['en', 'en-US'])
        target_langs: list of language codes (e.g., ['ca', 'ca-ES'])
        """
        if not os.path.exists(tmx_file):
            raise FileNotFoundError(f"File not found: {tmx_file}")

        print(f"--- Starting TMX indexation: {os.path.basename(tmx_file)} ---")
        
        batch = []
        total_processed = 0
        
        # Use iterparse to handle multi-gigabyte TMX files efficiently
        context = ET.iterparse(tmx_file, events=('end',))
        
        for event, elem in context:
            if elem.tag == 'tu':  # Translation Unit
                src_text = None
                tgt_text = None
                
                for tuv in elem.findall('tuv'):
                    # Get language code (xml:lang or lang)
                    lang = tuv.get('{http://www.w3.org/XML/1998/namespace}lang') or tuv.get('lang')
                    
                    if lang in source_langs:
                        seg = tuv.find('seg')
                        if seg is not None:
                            # Extract all inner text, ignoring internal tags
                            src_text = "".join(seg.itertext())
                    
                    elif lang in target_langs:
                        seg = tuv.find('seg')
                        if seg is not None:
                            tgt_text = "".join(seg.itertext())
                
                if src_text and tgt_text:
                    batch.append((src_text, tgt_text))
                    
                    if len(batch) >= batch_size:
                        self._insert_batch(batch)
                        total_processed += len(batch)
                        print(f"\r> Indexed translation units (TU): {total_processed:,}", end="", flush=True)
                        batch = []
                
                # Free memory of the processed element
                elem.clear()
                
        # Insert any remaining batch elements
        if batch:
            self._insert_batch(batch)
            total_processed += len(batch)
            print(f"\r> Indexed translation units (TU): {total_processed:,}", end="", flush=True)

        print(f"\nTMX indexation completed.")
        self.prune_common_ngrams(threshold_percent=1.0)
        self.optimize()
        
    def index_tabtxt(self, tabtxt_file, reverse=False, batch_size=10000):
        """
        Indexes a tabulated text file (TSV), compatible with .txt and .txt.gz.
        Expected format per line: source_text \t target_text
        
        reverse: If True, treats the 1st column as target and the 2nd as source.
        """
        if not os.path.exists(tabtxt_file):
            raise FileNotFoundError(f"Tabulated file not found: {tabtxt_file}")

        print(f"\n--- Starting TabTxt indexation: {os.path.basename(tabtxt_file)} ---")
        
        is_gz = tabtxt_file.endswith('.gz')
        open_func = gzip.open if is_gz else open
        mode = 'rt' if is_gz else 'r'

        batch = []
        total_processed = 0

        try:
            with open_func(tabtxt_file, mode, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    parts = line.split('\t')
                    if len(parts) < 2:
                        continue # Ignore malformed or empty lines
                    
                    col1, col2 = parts[0].strip(), parts[1].strip()
                    
                    src_text = col2 if reverse else col1
                    tgt_text = col1 if reverse else col2

                    if src_text and tgt_text:
                        batch.append((src_text, tgt_text))

                    if len(batch) >= batch_size:
                        self._insert_batch(batch)
                        total_processed += len(batch)
                        print(f"\r> Indexed segments: {total_processed:,}", end="", flush=True)
                        batch = []

            if batch:
                self._insert_batch(batch)
                total_processed += len(batch)
                print(f"\r> Indexed segments: {total_processed:,}", end="", flush=True)

        except Exception as e:
            print(f"\n[Error reading tabbed file]: {e}")
            raise

        print(f"\nTabTxt indexation completed.")
        self.prune_common_ngrams(threshold_percent=1.0)
        self.optimize()

    def search(self, query_text, min_similarity=70.0, max_candidates=100):
        """Ultra-fast fuzzy search with early exit and shortcut for 100% Matches."""
        query_norm = self._normalize(query_text)
        if not query_norm: return []

        # -----------------------------------------------------------------
        # SHORTCUT: Exact Search (100% Match) via idx_segments_source
        # -----------------------------------------------------------------
        self.cursor.execute("""
            SELECT target_text FROM segments 
            WHERE source_text = ? COLLATE NOCASE
            LIMIT ?
        """, (query_norm, max_candidates))
        
        exact_matches = self.cursor.fetchall()
        if exact_matches:
            return [(row[0], 100.0) for row in exact_matches]

        # Early exit if 100% similarity requested but not found above
        if min_similarity >= 100.0:
            return []

        # -----------------------------------------------------------------
        # FUZZY SEARCH (Only if min_similarity < 100)
        # -----------------------------------------------------------------
        query_ngrams = list(self._get_ngrams(query_norm))
        if not query_ngrams: return []

        # 1. Get n-gram IDs that are NOT blacklisted
        placeholders = ','.join(['?'] * len(query_ngrams))
        self.cursor.execute(f"""
            SELECT id FROM vocab 
            WHERE ngram IN ({placeholders})
              AND id NOT IN (SELECT vocab_id FROM ngrams_blacklist)
        """, query_ngrams)
        vocab_ids = [r[0] for r in self.cursor.fetchall()]
        
        if not vocab_ids: return []

        # 2. Direct search on relation table with length margin
        margin = int(len(query_norm) * (1 - min_similarity / 100) + 2)
        placeholders_ids = ','.join(['?'] * len(vocab_ids))
        
        sql = f"""
            SELECT s.source_text, s.target_text, COUNT(n.vocab_id) as hits
            FROM ngrams n
            JOIN segments s ON n.segment_id = s.id
            WHERE n.vocab_id IN ({placeholders_ids})
              AND s.source_len BETWEEN ? AND ?
            GROUP BY n.segment_id
            ORDER BY hits DESC
            LIMIT ?
        """
        params = vocab_ids + [len(query_norm) - margin, len(query_norm) + margin, max_candidates]
        self.cursor.execute(sql, params)
        
        results = []
        q_lower = query_norm.lower()
        for src_tm, tgt_tm, hits in self.cursor.fetchall():
            score = fuzz.ratio(q_lower, src_tm.lower())
            if score >= min_similarity:
                results.append((tgt_tm, score))
        
        return sorted(results, key=lambda x: x[1], reverse=True)

    def get_stats(self):
        """Returns a summary of the translation memory status."""
        self.cursor.execute("SELECT COUNT(*) FROM segments")
        segs = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT COUNT(*) FROM ngrams_blacklist")
        bl = self.cursor.fetchone()[0]
        return {"segments": segs, "blacklisted_ngrams": bl}

    def close(self):
        """Commits changes, clears cache, and closes the connection."""
        self.conn.commit()
        self.vocab_cache.clear()
        self.conn.close()
        
    def create_submemory(self, source_input, output_tmx_path, min_similarity, sl, tl):
        """
        Creates a smaller TMX file from the database based on a reference text.
        
        source_input: Can be a list of strings OR a path to an .xliff / .xlf file.
        output_tmx_path: Path where the resulting TMX file will be saved.
        min_similarity: Similarity threshold for filtering (e.g., 75.0).
        sl: Source language code for the TMX header (e.g., 'en').
        tl: Target language code for the TMX header (e.g., 'ca').
        """
        segments_to_search = []

        # 1. Detect input type (List or XLIFF / XLF)
        if isinstance(source_input, str) and source_input.lower().endswith(('.xliff', '.xlf')):
            if not os.path.exists(source_input):
                raise FileNotFoundError(f"XLIFF/XLF file not found: {source_input}")
            print(f"\n> Extracting segments from source file: {os.path.basename(source_input)}")
            
            try:
                tree = ET.parse(source_input)
                root = tree.getroot()
                for source_elem in root.iter():
                    if source_elem.tag.endswith('source') and source_elem.text:
                        text_clean = source_elem.text.strip()
                        if text_clean:
                            segments_to_search.append(text_clean)
            except Exception as e:
                print(f"[Error reading XLIFF/XLF file]: {e}")
                raise
        elif isinstance(source_input, list):
            segments_to_search = [s.strip() for s in source_input if s and s.strip()]
        else:
            raise ValueError("source_input must be a list of strings or a path to a .xliff/.xlf file")

        if not segments_to_search:
            print("> No segments found to search. Operation cancelled.")
            return

        print(f"> Loaded {len(segments_to_search)} segments to process.")
        print(f"> Searching matches in database (Min: {min_similarity}%)...")

        elements_afegits = set()
        total_tus = 0

        # 2. Generate TMX structure line by line (Stream mode)
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")
        
        try:
            with open(output_tmx_path, 'w', encoding='utf-8') as tmx:
                tmx.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                tmx.write('<!DOCTYPE tmx SYSTEM "tmx14.dtd">\n')
                tmx.write('<tmx version="1.4">\n')
                tmx.write(f'  <header creationtool="MTUOC" creationtoolversion="1.0" ')
                tmx.write(f'datatype="PlainText" segtype="sentence" adminlang="en" ')
                tmx.write(f'srclang="{sl}" o-tmf="MTUOC-DB" creationdate="{timestamp}">\n')
                tmx.write('  </header>\n')
                tmx.write('  <body>\n')

                # 3. Perform searches and write TUs (Translation Units)
                for i, query in enumerate(segments_to_search):
                    candidates = self.search(query, min_similarity=min_similarity, max_candidates=5)
                    query_norm = self._normalize(query)

                    for tgt_text, score in candidates:
                        clau_tu = (query_norm, tgt_text)
                        if clau_tu in elements_afegits:
                            continue
                        
                        elements_afegits.add(clau_tu)
                        
                        src_xml = query_norm.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                        tgt_xml = tgt_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

                        tmx.write('    <tu>\n')
                        tmx.write(f'      <tuv xml:lang="{sl}">\n')
                        tmx.write(f'        <seg>{src_xml}</seg>\n')
                        tmx.write('      </tuv>\n')
                        tmx.write(f'      <tuv xml:lang="{tl}">\n')
                        tmx.write(f'        <seg>{tgt_xml}</seg>\n')
                        tmx.write('      </tuv>\n')
                        tmx.write('    </tu>\n')
                        
                        total_tus += 1

                    if (i + 1) % 100 == 0 or (i + 1) == len(segments_to_search):
                        print(f"\r> Progress: {i+1}/{len(segments_to_search)} sentences processed.", end="", flush=True)

                tmx.write('  </body>\n')
                tmx.write('</tmx>\n')

            print(f"\n> Submemory created at: {output_tmx_path}")
            print(f"> Total translation units (TU): {total_tus:,}")

        except Exception as e:
            print(f"\n[Error writing TMX file]: {e}")
            if os.path.exists(output_tmx_path):
                os.remove(output_tmx_path)
            raise


if __name__ == "__main__":
    import argparse

    # Main parser
    parser = argparse.ArgumentParser(
        description="MTUOC Translation Memory Management Tool.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--db", 
        required=True, 
        help="Path to the SQLite translation memory database file."
    )
    
    # Subparsers for actions
    subparsers = parser.add_subparsers(dest="action", required=True, help="Available actions")

    # Action: index_moses
    p_moses = subparsers.add_parser("index_moses", help="Index a Moses corpus (separate source/target files).")
    p_moses.add_argument("--src_file", required=True, help="Path to the source language file.")
    p_moses.add_argument("--tgt_file", required=True, help="Path to the target language file.")
    p_moses.add_argument("--batch_size", type=int, default=10000, help="Batch size for atomic database insertions.")

    # Action: index_tmx
    p_tmx = subparsers.add_parser("index_tmx", help="Index a TMX translation memory file.")
    p_tmx.add_argument("--tmx_file", required=True, help="Path to the TMX file.")
    p_tmx.add_argument("--src_langs", required=True, nargs="+", help="List of source language codes (e.g., en en-US ENG).")
    p_tmx.add_argument("--tgt_langs", required=True, nargs="+", help="List of target language codes (e.g., ca ca-ES CAT).")
    p_tmx.add_argument("--batch_size", type=int, default=5000, help="Batch size for TMX parsing and insertion.")

    # Action: index_tabtxt
    p_tabtxt = subparsers.add_parser("index_tabtxt", help="Index a tabulated text file (.txt or .txt.gz).")
    p_tabtxt.add_argument("--tabtxt_file", required=True, help="Path to the tabulated text file.")
    p_tabtxt.add_argument("--reverse", action="store_true", help="If set, swaps columns: treats 1st column as target and 2nd as source.")
    p_tabtxt.add_argument("--batch_size", type=int, default=10000, help="Batch size for tabulated text processing.")

    # Action: search
    p_search = subparsers.add_parser("search", help="Perform an ultra-fast fuzzy or exact search in the TM.")
    p_search.add_argument("--query", required=True, help="The source sentence text to search for.")
    p_search.add_argument("--min_similarity", type=float, default=70.0, help="Minimum similarity percentage threshold (0.0 to 100.0).")
    p_search.add_argument("--max_candidates", type=int, default=100, help="Maximum number of translation candidates to return.")

    # Action: create_submemory
    p_sub = subparsers.add_parser("create_submemory", help="Extract a smaller TMX project sub-memory from a giant TM.")
    p_sub.add_argument("--input", required=True, help="Path to an XLIFF/XLF file OR a single text file containing one source sentence per line.")
    p_sub.add_argument("--output_tmx", required=True, help="Path where the output TMX sub-memory file will be saved.")
    p_sub.add_argument("--min_similarity", type=float, default=70.0, help="Minimum similarity threshold to include a match in the sub-memory.")
    p_sub.add_argument("--sl", required=True, help="Source language code attribute for the TMX header (e.g., en).")
    p_sub.add_argument("--tl", required=True, help="Target language code attribute for the TMX header (e.g., ca).")

    # Parse arguments
    args = parser.parse_args()

    # Initialize the Translation Memory
    tm = MTUOC_TranslationMemory(args.db)

    try:
        if args.action == "index_moses":
            tm.index_moses(source_file=args.src_file, target_file=args.tgt_file, batch_size=args.batch_size)
            
        elif args.action == "index_tmx":
            tm.index_tmx(tmx_file=args.tmx_file, source_langs=args.src_langs, target_langs=args.tgt_langs, batch_size=args.batch_size)
            
        elif args.action == "index_tabtxt":
            tm.index_tabtxt(tabtxt_file=args.tabtxt_file, reverse=args.reverse, batch_size=args.batch_size)
            
        elif args.action == "search":
            results = tm.search(query_text=args.query, min_similarity=args.min_similarity, max_candidates=args.max_candidates)
            print(f"\nSearch results for: '{args.query}' (Min Sim: {args.min_similarity}%)")
            print("-" * 80)
            if not results:
                print("No matches found.")
            for tgt, score in results:
                print(f"[{score:.1f}%] {tgt}")
            print("-" * 80)
            
        elif args.action == "create_submemory":
            source_input = args.input
            if os.path.exists(args.input) and args.input.lower().endswith('.txt'):
                print(f"\n> Reading reference segments from text file: {os.path.basename(args.input)}")
                with open(args.input, 'r', encoding='utf-8') as f:
                    source_input = [line.strip() for line in f if line.strip()]
            
            tm.create_submemory(
                source_input=source_input,
                output_tmx_path=args.output_tmx,
                min_similarity=args.min_similarity,
                sl=args.sl,
                tl=args.tl
            )

    except Exception as e:
        print(f"\n[Execution Error]: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        tm.close()
