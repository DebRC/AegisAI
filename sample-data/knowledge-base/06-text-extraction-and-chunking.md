# Text extraction and chunking

Workers extract supported TXT, Markdown, PDF, and DOCX files into normalized
text blocks with source locations. A PDF location records pages; a DOCX location
records paragraphs; plain text and Markdown retain traceable offsets.

The chunker creates ordered chunks around a target of 1,200 characters with a
200-character overlap. It prefers natural boundaries but can split a very long
unbroken sequence safely. Each chunk keeps its ordinal, offsets, source
locations, and parent extraction identity.

Extraction failures preserve a safe failure state rather than leaking parser
details to API clients. A replacement extraction atomically supersedes old
chunks when reprocessing succeeds.
