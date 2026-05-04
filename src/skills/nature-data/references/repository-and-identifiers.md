# Repository and Identifiers

Use this file when selecting repositories, checking accession strategy, or writing dataset
citations.

## Repository decision tree

1. Use a mandated repository when the data type requires it.
2. If no mandate applies, use a discipline-specific, community-recognised repository.
3. If no domain repository fits, use a trusted generalist or institutional repository that provides
   persistent identifiers and durable metadata.
4. Do not use personal websites, lab websites, ad hoc cloud folders, or unpublished private drives as
   the only availability route.
5. For very large data, use a repository or institutional infrastructure that can preserve metadata
   and provide clear access instructions even if bulk files require special transfer.

## What a repository record should provide

- persistent identifier: DOI, accession, Handle, ARK, or equivalent stable record
- public landing page with title, creators, abstract/description, repository, date, version, licence
- file list with sizes and formats
- README or data dictionary
- provenance and processing description
- relation to the manuscript and related code
- clear access procedure for restricted data
- versioning or update policy

## Common repository categories

Choose according to field norms; this list is not exhaustive.

| Data type | Typical repository pattern |
|---|---|
| Sequencing / gene expression | GEO, SRA, ENA, ArrayExpress or field-specific omics archive |
| Protein/nucleic acid structures | wwPDB / PDB |
| Small-molecule crystallography | CCDC or other crystallographic archive required by the journal |
| Proteomics | PRIDE or ProteomeXchange member repository |
| Metabolomics | MetaboLights or domain archive |
| Neuroimaging | OpenNeuro, DANDI, NDA, or controlled-access archive when required |
| Clinical or sensitive human data | controlled-access repository such as dbGaP, EGA, controlled institutional archive, or data access committee |
| Earth/environment/space science | PANGAEA, NASA/NOAA/ESA data centres, domain observatories |
| Social science | ICPSR, Dataverse, UK Data Service, OpenICPSR, OSF where appropriate |
| General datasets | Dryad, Zenodo, Figshare, OSF, institutional repository with DOI support |

Always check the target journal and funder because some data types have mandatory repositories.

## Identifier rules

- Prefer final public identifiers before submission.
- If the record is private during review, provide an anonymous reviewer link when the repository
  supports it.
- Do not cite temporary sharing links as dataset identifiers.
- Include accession numbers exactly as assigned by the repository.
- Use one identifier per coherent dataset record; avoid burying unrelated data under one unclear DOI.
- Version datasets when files change after review or publication.
- If the dataset has a DOI, cite the DOI rather than only the repository URL.

## Dataset citation pattern

Dataset references should include the minimum DataCite-style elements:

```text
[Creator(s)] ([Publication year]) [Dataset title]. [Repository]. [Identifier].
```

Add version when meaningful:

```text
[Creator(s)] ([Year]) [Dataset title], version [version]. [Repository]. [DOI/accession].
```

For reused public data, cite the dataset in the reference list when the dataset supports conclusions.
Mentioning it only in the Data Availability statement may be insufficient.

## Repository readiness checklist

Before submission:

- DOI/accession resolves to the intended landing page
- title matches manuscript terminology
- creators and affiliations are correct
- licence is present and compatible with intended reuse
- files open without proprietary software where possible
- README explains columns, units, missing values, transformations, and scripts
- figure source data are clearly mapped to figure panels
- restrictions and access conditions match the manuscript statement
- embargo/private links have been tested outside the author account

## Red flags

- "Data available on GitHub" without release DOI or archive
- repository record has no licence
- uploaded zip file has no README or file manifest
- accession exists but is not public, not under embargo, and not available to reviewers
- filenames use local analysis shorthand that readers cannot interpret
- manuscript cites one dataset but results depend on several unlisted secondary sources
