// Monaco Editor for BIRD + Jinja2 template editing
// Loads from jsDelivr CDN — no bundling needed

const MONACO_CDN = "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min"

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script")
    s.src = src
    s.onload = resolve
    s.onerror = reject
    document.head.appendChild(s)
  })
}

async function initMonaco() {
  const textarea = document.getElementById("editor-content")
  if (!textarea) return

  // Load Monaco AMD loader
  await loadScript(`${MONACO_CDN}/vs/loader.js`)

  window.require.config({ paths: { vs: `${MONACO_CDN}/vs` } })

  window.require(["vs/editor/editor.main"], function (monaco) {
    // ── Register BIRD + Jinja2 language ──────────────────────────────

    monaco.languages.register({ id: "bird-jinja2" })

    monaco.languages.setMonarchTokensProvider("bird-jinja2", {
      defaultToken: "",
      ignoreCase: false,

      jinjaKeywords: [
        "for", "endfor", "if", "elif", "else", "endif", "block", "endblock",
        "macro", "endmacro", "call", "endcall", "set", "include", "import",
        "from", "extends", "with", "endwith", "raw", "endraw", "filter",
        "endfilter", "do", "continue", "break", "is", "not", "and", "or",
        "in", "as", "true", "false", "none", "True", "False", "None",
        "ignore", "missing", "recursive", "scoped",
      ],

      jinjaFilters: [
        "ipaddr", "bird_str", "prefixlist",
        "default", "length", "join", "upper", "lower", "trim", "replace",
        "int", "float", "string", "list", "first", "last", "sort", "unique",
        "map", "select", "reject", "round", "abs", "capitalize", "escape",
        "safe", "tojson", "truncate",
      ],

      birdKeywords: [
        "protocol", "template", "router", "table", "filter", "function",
        "define", "include", "import", "from", "ipv4", "ipv6", "channel",
        "bgp", "device", "kernel", "direct", "static", "pipe", "ospf",
        "rip", "bfd", "local", "neighbor", "as", "multihop", "passive",
        "disabled", "preference", "export", "import", "all", "none",
        "where", "accept", "reject", "return", "true", "false", "if",
        "else", "then", "case", "print", "log", "scan", "time", "add",
        "paths", "secondary", "limit", "action", "block", "restart",
        "warn", "disable", "after", "max", "prefix", "id",
      ],

      birdTypes: [
        "int", "bool", "ip", "prefix", "pair", "quad", "ec", "lc",
        "string", "bgpmask", "bgppath", "clist", "eclist", "lclist",
        "net", "rd", "set",
      ],

      tokenizer: {
        root: [
          // Jinja2 comment
          [/\{#/, "comment.jinja", "@jinjaComment"],
          // Jinja2 expression
          [/\{\{/, "delimiter.jinja.expr", "@jinjaExpr"],
          // Jinja2 statement
          [/\{%[-~]?/, "delimiter.jinja.stmt", "@jinjaStmt"],
          // BIRD line comment
          [/#.*$/, "comment.bird"],
          // BIRD string
          [/"/, "string.bird", "@birdString"],
          // BIRD number
          [/\d+(\.\d+)?/, "number.bird"],
          // BIRD identifier/keyword
          [/[a-zA-Z_]\w*/, {
            cases: {
              "@birdKeywords": "keyword.bird",
              "@birdTypes": "type.bird",
              "@default": "identifier.bird",
            }
          }],
          // BIRD operators & punctuation
          [/[{}()[\];,=~!<>+\-*\/&|?:.]/, "delimiter.bird"],
        ],

        jinjaComment: [
          [/#\}/, "comment.jinja", "@pop"],
          [/./, "comment.jinja"],
        ],

        jinjaExpr: [
          [/\}\}/, "delimiter.jinja.expr", "@pop"],
          [/\|/, "operator.jinja.pipe"],
          [/\./, "operator.jinja.dot"],
          [/"/, "string.jinja", "@jinjaString_dq"],
          [/'/, "string.jinja", "@jinjaString_sq"],
          [/\d+(\.\d+)?/, "number.jinja"],
          [/[a-zA-Z_]\w*/, {
            cases: {
              "@jinjaKeywords": "keyword.jinja",
              "@jinjaFilters": "function.jinja",
              "@default": "variable.jinja",
            }
          }],
          [/[()[\],=!<>+\-*\/%:~]/, "operator.jinja"],
          [/\s+/, ""],
        ],

        jinjaStmt: [
          [/[-~]?%\}/, "delimiter.jinja.stmt", "@pop"],
          [/\|/, "operator.jinja.pipe"],
          [/\./, "operator.jinja.dot"],
          [/"/, "string.jinja", "@jinjaString_dq"],
          [/'/, "string.jinja", "@jinjaString_sq"],
          [/\d+(\.\d+)?/, "number.jinja"],
          [/[a-zA-Z_]\w*/, {
            cases: {
              "@jinjaKeywords": "keyword.jinja",
              "@jinjaFilters": "function.jinja",
              "@default": "variable.jinja",
            }
          }],
          [/[()[\],=!<>+\-*\/%:~]/, "operator.jinja"],
          [/\s+/, ""],
        ],

        jinjaString_dq: [
          [/[^"]+/, "string.jinja"],
          [/"/, "string.jinja", "@pop"],
        ],
        jinjaString_sq: [
          [/[^']+/, "string.jinja"],
          [/'/, "string.jinja", "@pop"],
        ],
        birdString: [
          [/[^"]+/, "string.bird"],
          [/"/, "string.bird", "@pop"],
        ],
      },
    })

    // ── Custom theme rules ───────────────────────────────────────────

    monaco.editor.defineTheme("ixforge-dark", {
      base: "vs-dark",
      inherit: true,
      rules: [
        { token: "comment.jinja", foreground: "6A9955", fontStyle: "italic" },
        { token: "comment.bird", foreground: "6A9955", fontStyle: "italic" },
        { token: "delimiter.jinja.expr", foreground: "DCDCAA", fontStyle: "bold" },
        { token: "delimiter.jinja.stmt", foreground: "C586C0", fontStyle: "bold" },
        { token: "keyword.jinja", foreground: "C586C0" },
        { token: "variable.jinja", foreground: "9CDCFE" },
        { token: "function.jinja", foreground: "DCDCAA" },
        { token: "operator.jinja.pipe", foreground: "D4D4D4" },
        { token: "operator.jinja.dot", foreground: "D4D4D4" },
        { token: "operator.jinja", foreground: "D4D4D4" },
        { token: "string.jinja", foreground: "CE9178" },
        { token: "number.jinja", foreground: "B5CEA8" },
        { token: "keyword.bird", foreground: "569CD6" },
        { token: "type.bird", foreground: "4EC9B0" },
        { token: "identifier.bird", foreground: "D4D4D4" },
        { token: "string.bird", foreground: "CE9178" },
        { token: "number.bird", foreground: "B5CEA8" },
        { token: "delimiter.bird", foreground: "808080" },
      ],
      colors: {},
    })

    monaco.editor.defineTheme("ixforge-light", {
      base: "vs",
      inherit: true,
      rules: [
        { token: "comment.jinja", foreground: "008000", fontStyle: "italic" },
        { token: "comment.bird", foreground: "008000", fontStyle: "italic" },
        { token: "delimiter.jinja.expr", foreground: "795E26", fontStyle: "bold" },
        { token: "delimiter.jinja.stmt", foreground: "AF00DB", fontStyle: "bold" },
        { token: "keyword.jinja", foreground: "AF00DB" },
        { token: "variable.jinja", foreground: "001080" },
        { token: "function.jinja", foreground: "795E26" },
        { token: "operator.jinja.pipe", foreground: "000000" },
        { token: "operator.jinja.dot", foreground: "000000" },
        { token: "operator.jinja", foreground: "000000" },
        { token: "string.jinja", foreground: "A31515" },
        { token: "number.jinja", foreground: "098658" },
        { token: "keyword.bird", foreground: "0000FF" },
        { token: "type.bird", foreground: "267F99" },
        { token: "identifier.bird", foreground: "001080" },
        { token: "string.bird", foreground: "A31515" },
        { token: "number.bird", foreground: "098658" },
        { token: "delimiter.bird", foreground: "808080" },
      ],
      colors: {},
    })

    // ── Autocomplete ─────────────────────────────────────────────────

    monaco.languages.registerCompletionItemProvider("bird-jinja2", {
      triggerCharacters: ["{", "%", "|", "."],
      provideCompletionItems(model, position) {
        const word = model.getWordUntilPosition(position)
        const range = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        }

        const suggestions = [
          // Jinja2 block snippets
          ...["for", "if", "block", "macro", "include", "set", "with", "raw"].map(tag => ({
            label: `{% ${tag} %}`,
            kind: monaco.languages.CompletionItemKind.Snippet,
            insertText: tag === "for" ? "for ${1:item} in ${2:items} %}\n$0\n{% endfor" :
              tag === "if" ? "if ${1:condition} %}\n$0\n{% endif" :
              tag === "block" ? "block ${1:name} %}\n$0\n{% endblock" :
              tag === "macro" ? "macro ${1:name}(${2:args}) %}\n$0\n{% endmacro" :
              tag === "include" ? 'include "${1:file.j2}" ' :
              tag === "set" ? "set ${1:var} = ${2:value} " :
              tag === "with" ? "with ${1:var} = ${2:value} %}\n$0\n{% endwith" :
              "raw %}\n$0\n{% endraw",
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            documentation: `Jinja2 ${tag} block`,
            range,
          })),
          // Context variables
          ...[
            ["route_server", "Route server context object"],
            ["route_server.name", "RS display name"],
            ["route_server.ip_v4", "RS IPv4 address"],
            ["route_server.ip_v6", "RS IPv6 address"],
            ["route_server.asn", "IXP ASN number"],
            ["route_server.router_id", "BIRD router ID"],
            ["peers", "List of active BGP peers"],
            ["peer.protocol_name", "Sanitized BIRD protocol name"],
            ["peer.member_name", "Member display name"],
            ["peer.peer_ip", "Peer IP address"],
            ["peer.peer_asn", "Peer AS number"],
            ["peer.max_prefixes", "Max prefix limit (or None)"],
            ["af", "Address family: 4 or 6"],
            ["generated_at", "ISO timestamp of generation"],
            ["config_hash", "SHA-256 hash of config"],
          ].map(([label, doc]) => ({
            label,
            kind: monaco.languages.CompletionItemKind.Variable,
            insertText: label,
            documentation: doc,
            range,
          })),
          // Filters
          ...[
            ["ipaddr", "Format IP: |ipaddr('network'), |ipaddr('prefixlen')"],
            ["bird_str", "Sanitize string for BIRD config"],
            ["prefixlist", "Render prefix list definition"],
            ["default", "Set default value if undefined"],
            ["length", "Return length of sequence"],
            ["join", "Join sequence with separator"],
            ["upper", "Convert to uppercase"],
            ["lower", "Convert to lowercase"],
            ["trim", "Strip whitespace"],
            ["replace", "Replace substring"],
            ["int", "Convert to integer"],
            ["first", "First element of sequence"],
            ["last", "Last element of sequence"],
            ["sort", "Sort sequence"],
            ["round", "Round number"],
            ["safe", "Mark as safe HTML"],
            ["tojson", "Serialize to JSON"],
          ].map(([label, doc]) => ({
            label,
            kind: monaco.languages.CompletionItemKind.Function,
            insertText: label,
            documentation: doc,
            range,
          })),
        ]

        return { suggestions }
      },
    })

    // ── Create editor ────────────────────────────────────────────────

    const isDark = document.documentElement.classList.contains("dark")

    const parent = textarea.parentElement
    const editorDiv = document.createElement("div")
    editorDiv.style.height = "500px"
    editorDiv.style.borderRadius = "6px"
    editorDiv.style.overflow = "hidden"
    editorDiv.style.border = isDark ? "1px solid #333" : "1px solid #e0e0e0"
    parent.insertBefore(editorDiv, textarea)
    textarea.style.display = "none"

    const editor = monaco.editor.create(editorDiv, {
      value: textarea.value,
      language: "bird-jinja2",
      theme: isDark ? "ixforge-dark" : "ixforge-light",
      fontSize: 13,
      lineHeight: 20,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace",
      fontLigatures: true,
      minimap: { enabled: true, scale: 2 },
      scrollBeyondLastLine: false,
      renderWhitespace: "selection",
      bracketPairColorization: { enabled: true },
      guides: { bracketPairs: true, indentation: true },
      occurrencesHighlight: "singleFile",
      selectionHighlight: true,
      automaticLayout: true,
      tabSize: 4,
      insertSpaces: true,
      wordWrap: "off",
      smoothScrolling: true,
      cursorBlinking: "smooth",
      cursorSmoothCaretAnimation: "on",
      padding: { top: 8, bottom: 8 },
      suggest: {
        showKeywords: true,
        showFunctions: true,
        showVariables: true,
        showSnippets: true,
        preview: true,
      },
    })

    // Sync content to textarea
    let isDirty = false
    editor.onDidChangeModelContent(() => {
      textarea.value = editor.getValue()
      isDirty = true
    })

    // Warn on unsaved changes
    window.addEventListener("beforeunload", (e) => {
      if (isDirty) { e.preventDefault(); e.returnValue = "" }
    })

    const form = textarea.closest("form")
    if (form) form.addEventListener("submit", () => { isDirty = false })

    // Dark mode toggle
    const observer = new MutationObserver(() => {
      const dark = document.documentElement.classList.contains("dark")
      monaco.editor.setTheme(dark ? "ixforge-dark" : "ixforge-light")
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })
  })
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initMonaco)
} else {
  initMonaco()
}
