"""Download latest IMDb exports and save to data/. Used by download-exports workflow."""
import sys, traceback
from dotenv import load_dotenv
load_dotenv()
from fetch_ratings import download_exports

try:
    ratings, watchlist = download_exports()
    print(f"\nDone.\n  {ratings}\n  {watchlist}")
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
