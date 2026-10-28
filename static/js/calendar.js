// All navigation and entry links work without JavaScript. This only positions
// the desktop timeline near the first commitment, with some breathing room.
const calendar = document.querySelector(".calendar-scroll");
if (calendar && window.matchMedia("(min-width: 768px)").matches) {
  const minutes = Number(calendar.dataset.initialMinute);
  const scale = parseFloat(getComputedStyle(calendar).getPropertyValue("--calendar-minute-size"));
  if (Number.isFinite(minutes) && Number.isFinite(scale)) {
    calendar.scrollTop = minutes * scale;
  }
}
