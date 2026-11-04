<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ content: string }>();

function escapeHtml(value: string) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;").replace(/'/g, "&#039;");
}

function inline(value: string) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}

function render(value: string) {
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
  for (const line of lines) {
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
