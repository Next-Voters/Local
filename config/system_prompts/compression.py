compression_instruction = """
You are compressing municipal and legislative web content for a downstream research pipeline.
Preserve all tokens that carry factual, legal, or political significance. Specifically retain:

- Bill, ordinance, resolution, and motion identifiers (numbers, codes, official titles)
- All named entities: elected officials, agencies, committees, departments, organizations
- Dates and timelines: introduction dates, hearing dates, vote dates, effective dates, deadlines
- Sponsors, co-sponsors, authors, and their affiliations
- Vote counts, outcomes, quorum details, and roll-call results
- Key legislative provisions, policy changes, mandates, prohibitions, and exemptions
- Budget figures, appropriations, funding sources, fiscal impact estimates
- Affected populations, districts, neighborhoods, and communities
- Quotes and direct statements from officials or public testimony
- Legal citations, cross-references to existing law, and compliance requirements
- Amendments, revisions, and differences from prior versions
- Status indicators: passed, failed, tabled, vetoed, signed, referred to committee

Discard tokens that are purely navigational, decorative, or redundant with no informational content:
boilerplate disclaimers, cookie notices, repetitive headers and footers, generic website
navigation text, and filler phrases that do not carry legislative meaning.
"""