import { readonly, ref } from "vue";

export interface ToastMessage { id: number; text: string; kind: "success" | "error" | "info"; }
const messages = ref<ToastMessage[]>([]);
let nextId = 1;

export function useToast() {
  function show(text: string, kind: ToastMessage["kind"] = "info") {
    const id = nextId++;
    messages.value.push({ id, text, kind });
    window.setTimeout(() => { messages.value = messages.value.filter((item) => item.id !== id); }, 3500);
  }
  return { messages: readonly(messages), show, success: (text: string) => show(text, "success"), error: (text: string) => show(text, "error") };
}
