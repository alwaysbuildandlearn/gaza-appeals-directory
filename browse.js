const grid = document.querySelector("#appeals .grid");
const next = document.querySelector('.pagination a[rel="next"]');

if (grid && next) {
  next.addEventListener("click", async (event) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (next.getAttribute("aria-busy") === "true") return;
    const address = next.href;
    next.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(address);
      if (!response.ok) throw new Error("Page unavailable");
      const page = new DOMParser().parseFromString(await response.text(), "text/html");
      const cards = [...page.querySelectorAll("#appeals .grid .card")];
      if (!cards.length) throw new Error("Appeals unavailable");
      const more = page.querySelector('.pagination a[rel="next"]');
      const count = document.querySelector("#result-count");
      const start = count.textContent.split("–")[0];
      count.textContent = start + "–" + page.querySelector("#result-count").textContent.split("–")[1];
      grid.append(...cards);
      cards[0].querySelector("h3 a").focus();
      if (more) next.href = more.getAttribute("href");
      else next.remove();
    } catch {
      window.location.assign(address);
    } finally {
      next.removeAttribute("aria-busy");
    }
  });
}
