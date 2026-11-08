<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ content: string }>();

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;").replace(/'/g, "&#039;");
}

function inline(value: string): string {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}

function tableCells(line: string): string[] {
  let value = line.trim();
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|")) value = value.slice(0, -1);
  return value.split("|").map((cell) => cell.trim());
}

function isTableDelimiter(cells: string[]): boolean {
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function tableAlign(cell: string): "left" | "center" | "right" {
  const trimmed = cell.trim();
  if (trimmed.startsWith(":") && trimmed.endsWith(":")) return "center";
  if (trimmed.endsWith(":")) return "right";
  return "left";
}

function render(value: string): string {
  const lines = value.replace(/\r\n/g, "\n").split("\n");
  const output: string[] = [];
  let list: "ul" | "ol" | null = null;
  let code = false;
  const closeList = () => {
    if (list) {
      output.push(list === "ul" ? "</ul>" : "</ol>");
      list = null;
    }
  };
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    if (line.startsWith("```")) {
      closeList();
      output.push(code ? "</code></pre>" : "<pre><code>");
      code = !code;
      continue;
    }
    if (code) {
      output.push(`${escapeHtml(line)}\n`);
      continue;
    }
    const nextLine = lines[index + 1] ?? "";
    const headerCells = tableCells(line);
    const delimiterCells = tableCells(nextLine);
    if (line.includes("|") && nextLine.includes("|") && headerCells.length >= 2 && isTableDelimiter(delimiterCells)) {
      closeList();
      const rows: string[][] = [];
      let cursor = index + 2;
      while (cursor < lines.length && (lines[cursor] ?? "").includes("|")) {
        const cells = tableCells(lines[cursor] ?? "");
        if (!cells.length) break;
        rows.push(cells);
        cursor += 1;
      }
      const alignments = headerCells.map((_, cellIndex) => tableAlign(delimiterCells[cellIndex] || "---"));
      output.push(`<div class="markdown-table-wrap"><table><thead><tr>${headerCells.map((cell, cellIndex) => `<th style="text-align:${alignments[cellIndex]}">${inline(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${headerCells.map((_, cellIndex) => `<td style="text-align:${alignments[cellIndex]}">${inline(row[cellIndex] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      index = cursor - 1;
      continue;
    }
    const unordered = line.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      if (list !== "ul") {
        closeList();
        output.push("<ul>");
        list = "ul";
      }
      output.push(`<li>${inline(unordered[1] ?? "")}</li>`);
      continue;
    }
    const ordered = line.match(/^\d+\.\s+(.+)$/);
    if (ordered) {
      if (list !== "ol") {
        closeList();
        output.push("<ol>");
        list = "ol";
      }
      output.push(`<li>${inline(ordered[1] ?? "")}</li>`);
      continue;
    }
    closeList();
    if (line.startsWith("### ")) output.push(`<h3>${inline(line.slice(4))}</h3>`);
    else if (line.startsWith("## ")) output.push(`<h2>${inline(line.slice(3))}</h2>`);
    else if (line.startsWith("# ")) output.push(`<h1>${inline(line.slice(2))}</h1>`);
    else if (line.startsWith("> ")) output.push(`<blockquote>${inline(line.slice(2))}</blockquote>`);
    else if (line.trim()) output.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  if (code) output.push("</code></pre>");
  return output.join("");
}

const html = computed(() => render(props.content));
</script>

<template><div class="markdown-content" v-html="html" /></template>
