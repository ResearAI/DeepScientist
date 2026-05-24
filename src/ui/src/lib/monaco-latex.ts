"use client";

export const LATEX_LANGUAGE_ID = "latex-ds";
export const BIBTEX_LANGUAGE_ID = "bibtex-ds";

let configured = false;

function languageExists(monaco: any, id: string): boolean {
  const languages = monaco.languages.getLanguages?.() || [];
  return languages.some((item: { id: string }) => item.id === id);
}

export function ensureMonacoLatexLanguages(monaco: any) {
  if (!monaco?.languages || !monaco?.editor) return;
  if (!languageExists(monaco, LATEX_LANGUAGE_ID)) {
    monaco.languages.register({
      id: LATEX_LANGUAGE_ID,
      aliases: ["LaTeX", "latex", "tex"],
      extensions: [".tex", ".latex", ".sty", ".cls"],
      mimetypes: ["text/x-tex", "text/x-latex"],
    });
  }
  if (!languageExists(monaco, BIBTEX_LANGUAGE_ID)) {
    monaco.languages.register({
      id: BIBTEX_LANGUAGE_ID,
      aliases: ["BibTeX", "bibtex"],
      extensions: [".bib"],
      mimetypes: ["text/x-bibtex"],
    });
  }
  if (configured) return;

  monaco.languages.setLanguageConfiguration(LATEX_LANGUAGE_ID, {
    comments: {
      lineComment: "%",
      blockComment: ["\\begin{comment}", "\\end{comment}"],
    },
    brackets: [
      ["{", "}"],
      ["[", "]"],
      ["(", ")"],
    ],
    autoClosingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "(", close: ")" },
      { open: "$", close: "$", notIn: ["comment"] },
    ],
    surroundingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "(", close: ")" },
      { open: "$", close: "$" },
    ],
  });

  monaco.languages.setMonarchTokensProvider(LATEX_LANGUAGE_ID, {
    defaultToken: "",
    tokenPostfix: ".tex",
    tokenizer: {
      root: [
        [/\\begin\s*\{\s*comment\s*\}/, { token: "comment.block", next: "@commentBlock" }],
        [/%.*$/, "comment"],
        [/\\(?:begin|end|documentclass|usepackage|include|input|bibliography|bibliographystyle)\b/, "keyword"],
        [
          /\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph|caption|label)\b/,
          "keyword",
        ],
        [/\\(?:cite|citet|citep|autocite|parencite|ref|eqref|url|href)\b/, "type.identifier"],
        [/\\(?:textbf|textit|emph|underline|mathrm|mathbf|mathit|mathcal)\b/, "type.identifier"],
        [/\\[a-zA-Z@]+/, "identifier"],
        [/\\./, "identifier"],
        [/\\\[/, { token: "string.math", next: "@displayMathBracket" }],
        [/\\\(/, { token: "string.math", next: "@inlineMathParen" }],
        [/\$\$/, { token: "string.math", next: "@displayMathDollar" }],
        [/\$/, { token: "string.math", next: "@inlineMathDollar" }],
        [/[{}()[\]]/, "@brackets"],
        [/[&_#^~]/, "operator"],
      ],
      commentBlock: [
        [/\\end\s*\{\s*comment\s*\}/, { token: "comment.block", next: "@pop" }],
        [/.*$/, "comment.block"],
      ],
      inlineMathDollar: [
        [/%.*$/, "comment"],
        [/\$/, { token: "string.math", next: "@pop" }],
        [/\\[a-zA-Z@]+/, "identifier"],
        [/./, "string.math"],
      ],
      displayMathDollar: [
        [/%.*$/, "comment"],
        [/\$\$/, { token: "string.math", next: "@pop" }],
        [/\\[a-zA-Z@]+/, "identifier"],
        [/./, "string.math"],
      ],
      inlineMathParen: [
        [/%.*$/, "comment"],
        [/\\\)/, { token: "string.math", next: "@pop" }],
        [/\\[a-zA-Z@]+/, "identifier"],
        [/./, "string.math"],
      ],
      displayMathBracket: [
        [/%.*$/, "comment"],
        [/\\\]/, { token: "string.math", next: "@pop" }],
        [/\\[a-zA-Z@]+/, "identifier"],
        [/./, "string.math"],
      ],
    },
  });

  monaco.languages.setLanguageConfiguration(BIBTEX_LANGUAGE_ID, {
    comments: {
      lineComment: "%",
    },
    brackets: [
      ["{", "}"],
      ["[", "]"],
      ["(", ")"],
    ],
    autoClosingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "(", close: ")" },
      { open: '"', close: '"', notIn: ["comment", "string"] },
    ],
    surroundingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "(", close: ")" },
      { open: '"', close: '"' },
    ],
  });

  monaco.languages.setMonarchTokensProvider(BIBTEX_LANGUAGE_ID, {
    defaultToken: "",
    tokenPostfix: ".bib",
    tokenizer: {
      root: [
        [/%.*$/, "comment"],
        [/@(?:article|book|booklet|conference|inbook|incollection|inproceedings|manual|mastersthesis|misc|phdthesis|proceedings|techreport|unpublished|string|preamble|comment)\b/i, "keyword"],
        [/[a-zA-Z][\w-]*(?=\s*=)/, "attribute.name"],
        [/"([^"\\]|\\.)*$/, "string.invalid"],
        [/"/, { token: "string.quote", next: "@string" }],
        [/[{}()[\],=]/, "@brackets"],
      ],
      string: [
        [/[^\\"]+/, "string"],
        [/\\./, "string.escape"],
        [/"/, { token: "string.quote", next: "@pop" }],
      ],
    },
  });

  configured = true;
}
