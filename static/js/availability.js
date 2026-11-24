const copyAvailability = document.querySelector("[data-copy-availability]");
const employerText = document.querySelector("#employer-availability");
const copyStatus = document.querySelector("[data-copy-status]");

if (copyAvailability && employerText && copyStatus) {
  copyAvailability.hidden = false;
  copyAvailability.addEventListener("click", async () => {
    copyAvailability.disabled = true;
    try {
      if (!window.isSecureContext || !navigator.clipboard?.writeText) {
        throw new Error("Clipboard unavailable");
      }
      await navigator.clipboard.writeText(employerText.value);
      copyStatus.textContent = "Availability copied. Paste it into your message to an employer.";
    } catch {
      employerText.focus();
      employerText.select();
      employerText.setSelectionRange(0, employerText.value.length);
      copyStatus.textContent = "Text selected. Use your device's Copy action to copy the availability.";
    } finally {
      copyAvailability.disabled = false;
    }
  });
}
