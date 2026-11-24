document.querySelectorAll("[data-window-editor]").forEach((editor) => {
  const total = editor.querySelector(`[name="${editor.dataset.prefix}-TOTAL_FORMS"]`);
  const rows = editor.querySelector("[data-window-rows]");
  const template = editor.querySelector("[data-empty-window]");
  const status = editor.querySelector("[data-window-status]");
  editor.querySelector("[data-add-window]").addEventListener("click", (event) => {
    event.preventDefault();
    const index = Number(total.value);
    if (!Number.isInteger(index) || index < 0 || index >= 100) {
      status.textContent = "A schedule can contain up to 100 windows.";
      return;
    }
    const content = document.createElement("template");
    content.innerHTML = template.innerHTML.replaceAll("__prefix__", String(index));
    const row = content.content.firstElementChild;
    const legend = row.querySelector("legend");
    legend.textContent = `Window ${index + 1}`;
    rows.append(content.content);
    total.value = String(index + 1);
    status.textContent = "Window added. Enter its hours before saving.";
    row.querySelector("select, input:not([type=hidden])").focus();
  });
});
