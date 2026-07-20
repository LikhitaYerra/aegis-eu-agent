# Corpus

This directory contains a curated evaluation corpus drawn from official EUR-Lex versions of
Regulation (EU) 2024/1689 and Regulation (EU) 2016/679. Each Markdown document records its
instrument, provisions, official source URL, publication date, retrieval date, and jurisdiction.
The text is scoped to the provisions needed by the project's 10-question gold set; the source URL
remains authoritative.

Additional UTF-8 `.md` or `.txt` sources can be placed here. The loader ignores this README. Use
descriptive filenames because each stem becomes the document title and identifier.

Store the source URL, publication date, retrieval date, jurisdiction, and licence at the top of
each document. Prefer official EUR-Lex and regulator material over summaries. Do not add
copyrighted commercial commentary without permission.

When no corpus document is present, the agent uses a small built-in four-document EU sample so
that `python src/agent.py` remains runnable after a clean clone. Neither the sample nor this
curated coursework corpus replaces checking the complete consolidated legislation, later
delegated acts, Commission guidance, and applicable national law for real legal work.
