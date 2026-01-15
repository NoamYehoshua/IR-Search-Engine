# inverted_index_colab.py
"""
TEMPORARY SHIM (Pickle compatibility)

WHY THIS EXISTS:
- Existing index.pkl was pickled when InvertedIndex lived in module `inverted_index_colab`.
- Backend code uses `inverted_index_gcp.InvertedIndex`.

WHEN TO REMOVE:
- After rebuilding index.pkl using the same module name as the backend (recommended: inverted_index_gcp),
  AND verifying that loading index.pkl no longer raises ModuleNotFoundError.

HOW TO VERIFY REMOVAL:
- Delete this file and run: python -u main_test_index_cached.py
- If it works, you can remove this shim permanently.
"""

from inverted_index_gcp import InvertedIndex
