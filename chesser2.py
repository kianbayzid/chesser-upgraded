import chess
import chess.engine
import chess.pgn
import requests
import time
from typing import List, Dict, Optional, Tuple
import json
import os

# stockfish = Stockfish(path="C:\Users\Kian\Projects\chesser\chesser-upgraded\venv\stockfish-windows-x86-64-avx2.exe")
# stockfish.update_engine_parameters({
#     "Threads": 8,
#     "Hash": 1024,
# })

class LichessStockfishAnalyzer:
    def __init__(self, stockfish_path: str, min_games: int = 100):
        """
        Initialize the analyzer with Stockfish engine path.
        
        Args:
            stockfish_path: Path to the Stockfish executable
            min_games: Minimum number of games required to continue analyzing a position
        """
        self.stockfish_path = stockfish_path
        self.engine = None
        self.lichess_base_url = "https://explorer.lichess.ovh/lichess"
        self.min_games = min_games
        self.variation_counter = 0
        self.all_variations = []
        
    def __enter__(self):
        """Context manager entry - start the engine."""
        self.engine = chess.engine.SimpleEngine.popen_uci(self.stockfish_path)
        # Increase CPU and RAM usage
        self.engine.configure({
            "Threads": 8,
            "Hash": 2048
        })
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close the engine."""
        if self.engine:
            self.engine.quit()
    
    def get_lichess_moves(self, board: chess.Board, top_n: int = 10) -> List[Dict]:
        """
        Get the most common moves from Lichess opening database.
        
        Args:
            board: Current chess board position
            top_n: Number of top moves to retrieve
            
        Returns:
            List of move data from Lichess
        """
        fen = board.fen()
        params = {
            'fen': fen,
            'ratings': '1600,1800,2000,2200,2500',
            'speeds': 'blitz,rapid,classical',
            'moves': top_n
        }
        
        try:
            response = requests.get(self.lichess_base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            moves = []
            for move_data in data.get('moves', [])[:top_n]:
                total_games = move_data.get('white', 0) + move_data.get('draws', 0) + move_data.get('black', 0)
                
                # Only include moves with sufficient games
                if total_games >= self.min_games:
                    moves.append({
                        'uci': move_data['uci'],
                        'san': move_data['san'],
                        'games': total_games,
                        'white_wins': move_data.get('white', 0),
                        'draws': move_data.get('draws', 0),
                        'black_wins': move_data.get('black', 0)
                    })
            
            return moves
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching Lichess data: {e}")
            return []
        
        # Rate limiting
        time.sleep(0.5)
    
    def get_best_response(self, board: chess.Board, depth: int = 40) -> Optional[Dict]:
        """
        Get Stockfish's best response to the current position.
        
        Args:
            board: Chess board position to analyze
            depth: Analysis depth (default 40)
            
        Returns:
            Dictionary with best move and evaluation, or None if no move found
        """
        try:
            # Analyze the position at the specified depth
            result = self.engine.play(board, chess.engine.Limit(depth=depth))
            
            if result.move:
                # Get the evaluation after the best move
                temp_board = board.copy()
                temp_board.push(result.move)
                info = self.engine.analyse(temp_board, chess.engine.Limit(depth=20))
                
                score = info['score'].relative.score(mate_score=10000) if info['score'].relative else 0
                # Flip the score since we're looking from the other player's perspective
                score = -score
                
                return {
                    'move': result.move,
                    'uci': result.move.uci(),
                    'san': board.san(result.move),
                    'evaluation': score / 100  # Convert to pawns
                }
            
        except Exception as e:
            print(f"Error getting best response: {e}")
        
        return None
    
    def generate_pgn(self, moves: List[Tuple[chess.Move, str]], 
                     evaluation: float, variation_name: str = "") -> str:
        """
        Generate PGN for a specific variation.
        
        Args:
            moves: List of (move_object, san_notation) tuples
            evaluation: Evaluation after the last move
            variation_name: Name of the variation
            
        Returns:
            PGN string
        """
        game = chess.pgn.Game()
        
        # Set headers
        game.headers["Event"] = "Lichess Popular Moves vs Stockfish Best Response"
        game.headers["Result"] = "*"
        if variation_name:
            game.headers["Variation"] = variation_name
        
        # Add all moves
        node = game
        for move_obj, _ in moves:
            node = node.add_variation(move_obj)
        
        # Add evaluation comment
        node.comment = f"Stockfish (depth 40) evaluation: {evaluation:+.2f}"
        
        return str(game)
    
    def get_move_path_string(self, moves: List[Tuple[chess.Move, str]]) -> str:
        """Convert list of moves to a readable path string."""
        move_number = 1
        path = ""
        for i, (_, san) in enumerate(moves):
            if i % 2 == 0:  # White move
                path += f"{move_number}. {san} "
                move_number += 1
            else:  # Black move
                path += f"{san} "
        return path.strip()
    
    def analyze_position_recursive(self, board: chess.Board, 
                                 move_history: List[Tuple[chess.Move, str]], 
                                 depth_level: int = 0) -> None:
        """
        Recursively analyze positions, going deeper until Lichess database is exhausted.
        
        Args:
            board: Current board position
            move_history: List of (move_object, san_notation) tuples leading to this position
            depth_level: Current depth in the tree (for logging)
        """
        indent = "  " * depth_level
        current_path = self.get_move_path_string(move_history)
        
        # Get popular moves from Lichess
        print(f"\n{indent}Analyzing position after: {current_path}")
        lichess_moves = self.get_lichess_moves(board, top_n=10)
        
        if not lichess_moves:
            print(f"{indent}No more moves in database (< {self.min_games} games)")
            return
        
        print(f"{indent}Found {len(lichess_moves)} popular moves")
        
        # Analyze each popular move
        for i, move_data in enumerate(lichess_moves):
            print(f"\n{indent}Move {i+1}/{len(lichess_moves)}: {move_data['san']} ({move_data['games']:,} games)")
            
            # Make the popular move
            temp_board = board.copy()
            try:
                move = chess.Move.from_uci(move_data['uci'])
                temp_board.push(move)
                new_history = move_history + [(move, move_data['san'])]
            except Exception as e:
                print(f"{indent}  Error making move: {e}")
                continue
            
            # Get Stockfish's best response
            print(f"{indent}  Finding best response (depth 40)...")
            best_response = self.get_best_response(temp_board, depth=40)
            
            if best_response:
                print(f"{indent}  Best response: {best_response['san']} (eval: {best_response['evaluation']:+.2f})")
                
                # Create variation with the response
                self.variation_counter += 1
                response_move = chess.Move.from_uci(best_response['uci'])
                complete_history = new_history + [(response_move, best_response['san'])]
                
                # Generate PGN
                variation_name = f"Variation {self.variation_counter}"
                pgn = self.generate_pgn(complete_history, best_response['evaluation'], variation_name)
                
                # Save the variation
                filename = f"variation_{self.variation_counter}.pgn"
                with open(filename, "w") as f:
                    f.write(pgn)
                
                print(f"{indent}  Saved as {filename}")
                
                # Store variation info
                self.all_variations.append({
                    'number': self.variation_counter,
                    'moves': self.get_move_path_string(complete_history),
                    'evaluation': best_response['evaluation'],
                    'games': move_data['games'],
                    'depth': len(complete_history)
                })
                
                # Recursively analyze the position after the response
                temp_board.push(response_move)
                self.analyze_position_recursive(temp_board, complete_history, depth_level + 1)
            else:
                print(f"{indent}  Could not find best response")
    
    def analyze_position(self, pgn_moves: str) -> None:
        """
        Main analysis function that starts the recursive analysis.
        
        Args:
            pgn_moves: Starting moves in PGN format (e.g., "1. Nf3 d5 2. g3")
        """
        # Parse starting position
        board = chess.Board()
        move_history = []
        
        # Convert PGN to moves
        import io
        pgn_io = io.StringIO(pgn_moves)
        
        # Parse the starting moves
        try:
            game = chess.pgn.read_game(pgn_io)
            if game:
                for move in game.mainline_moves():
                    san = board.san(move)
                    move_history.append((move, san))
                    board.push(move)
            else:
                raise ValueError("Could not parse PGN")
        except:
            # Parse moves manually if PGN parsing fails
            board = chess.Board()
            move_history = []
            tokens = pgn_moves.replace(".", "").split()
            for token in tokens:
                if token.isdigit():
                    continue
                try:
                    move = board.parse_san(token)
                    move_history.append((move, token))
                    board.push(move)
                except Exception as e:
                    print(f"Could not parse move: {token} - {e}")
        
        print(f"Starting position: {pgn_moves}")
        print(f"FEN: {board.fen()}")
        print(f"Minimum games threshold: {self.min_games}")
        print("=" * 60)
        
        # Start recursive analysis
        self.analyze_position_recursive(board, move_history, depth_level=0)


def main():
    # Configuration
    STOCKFISH_PATH = r"C:\Users\Kian\Projects\chesser\chesser-upgraded\venv\stockfish-windows-x86-64-avx2.exe"  # Update this path
    STARTING_POSITION = "1. Nf3 d5 2. g3"
    MIN_GAMES = 1 # Minimum games required to analyze a position
    
    print("Lichess Popular Moves vs Stockfish Best Response Analyzer")
    print("Recursive Deep Analysis Version")
    print("=" * 60)
    print(f"Starting position: {STARTING_POSITION}")
    print(f"This will recursively analyze all positions until the Lichess")
    print(f"database has fewer than {MIN_GAMES} games for a position.")
    print("=" * 60)
    
    # Create output directory
    output_dir = f"analysis_{STARTING_POSITION.replace(' ', '_').replace('.', '')}"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    os.chdir(output_dir)
    
    # Run analysis
    with LichessStockfishAnalyzer(STOCKFISH_PATH, min_games=MIN_GAMES) as analyzer:
        analyzer.analyze_position(STARTING_POSITION)
        
        # Save summary
        print("\n" + "=" * 60)
        print(f"Analysis complete! Generated {analyzer.variation_counter} variations")
        
        # Save detailed summary
        summary = {
            'starting_position': STARTING_POSITION,
            'total_variations': analyzer.variation_counter,
            'min_games_threshold': MIN_GAMES,
            'analysis_depth': 40,
            'variations': analyzer.all_variations
        }
        
        with open("complete_analysis.json", "w") as f:
            json.dump(summary, f, indent=2)
        
        # Create a tree view summary
        with open("variation_tree.txt", "w") as f:
            f.write(f"Opening Tree for: {STARTING_POSITION}\n")
            f.write("=" * 60 + "\n\n")
            
            # Group variations by depth
            max_depth = max(v['depth'] for v in analyzer.all_variations) if analyzer.all_variations else 0
            
            for depth in range(2, max_depth + 1, 2):  # Each full move is 2 plies
                depth_vars = [v for v in analyzer.all_variations if v['depth'] == depth]
                if depth_vars:
                    f.write(f"\nDepth {depth//2} moves ({depth} plies):\n")
                    f.write("-" * 40 + "\n")
                    for var in depth_vars:
                        f.write(f"Var {var['number']:3d}: {var['moves']} "
                               f"(eval: {var['evaluation']:+.2f}, {var['games']:,} games)\n")
        
        print(f"\nFiles created in '{output_dir}' directory:")
        print(f"- {analyzer.variation_counter} PGN files (variation_1.pgn through variation_{analyzer.variation_counter}.pgn)")
        print(f"- complete_analysis.json (detailed summary)")
        print(f"- variation_tree.txt (tree structure view)")


if __name__ == "__main__":
    main()
# pip install python-chess
# pip install requests