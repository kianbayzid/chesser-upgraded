Lichess Popular Moves vs Stockfish Best Response Analyzer:
  * A recursive chess opening analyzer that:
  * Pulls popular moves from the Lichess opening database
  * Computes Stockfish’s best response
  * Recursively explores the opening tree
  * Saves every variation as a PGN
  * Supports resume capability with progress caching
Features:
  * Queries Lichess Opening Explorer API
  * Uses Stockfish (UCI engine) for best responses
  * Recursively explores opening trees
  * Resume support via progress.json
  * Generates individual PGN files for every variation
  * Outputs structured JSON summary
  * Creates a tree-view text summary
  * Caching to avoid re-analyzing positions
Requirements:
  * pip install python-chess
  * pip install requests
