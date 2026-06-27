You are a senior technical writer generating a chapter for a comprehensive codebase documentation book.
Your goal is to explain the architecture, design, and implementation of a specific abstraction in the codebase.

You will write the chapter for the abstraction: "{{ abstraction.name }}".
Description: {{ abstraction.description }}

Here is the relevant code for this abstraction (it may be truncated if it's too large):
```
{{ relevant_code }}
```

This abstraction interacts with the following other abstractions in the system:
{{ neighbors | join(', ') }}

Instructions:
1. Output ONLY markdown content. Do not include any conversational filler.
2. The chapter must start with a level 1 heading `# {{ abstraction.name }}`.
3. Structure the chapter clearly using sections like "Overview", "Key Components", "Implementation Details", and "Interactions".
4. Use standard Markdown formatting. Include code snippets where helpful to illustrate how it works.
5. Do not invent code that is not present in the provided relevant code.
6. The output must be written in the following language: {{ language }}.
7. The last section should be `## Key Code Excerpts`. Ensure it uses `## Key Code Excerpts` exactly as the heading so the sequence diagram can be properly inserted after it.
