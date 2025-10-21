# Roster Extractor (fix Period -> str)

- Fixes: `'Period' object has no attribute 'astype'` by using `str(period)`.
- Automatically reads the **Směny** sheet (fallback: first sheet).
- Month selector defaults to current month if present; days ascending; week jump buttons included.
