/** Navegación sencilla de la presentación, sin dependencias externas. */

const slides = Array.from(document.querySelectorAll(".slide"));
const counter = document.getElementById("counter");
const progressBar = document.getElementById("progress-bar");
const prevButton = document.getElementById("prev");
const nextButton = document.getElementById("next");
const printButton = document.getElementById("print");

let indice = 0;

function pad(numero) {
  return String(numero).padStart(2, "0");
}

function mostrar(nuevoIndice) {
  indice = Math.max(0, Math.min(slides.length - 1, nuevoIndice));

  slides.forEach((slide, posicion) => {
    slide.classList.toggle("active", posicion === indice);
  });

  const total = slides.length;
  counter.textContent = `${pad(indice + 1)} / ${pad(total)}`;
  progressBar.style.width = `${((indice + 1) / total) * 100}%`;

  prevButton.disabled = indice === 0;
  nextButton.disabled = indice === total - 1;

  document.title = `${slides[indice].dataset.title || "Diapositiva"} · Clicker por cámara`;
}

prevButton.addEventListener("click", () => mostrar(indice - 1));
nextButton.addEventListener("click", () => mostrar(indice + 1));
printButton.addEventListener("click", () => window.print());

document.addEventListener("keydown", (evento) => {
  if (["ArrowRight", "PageDown", " "].includes(evento.key)) {
    evento.preventDefault();
    mostrar(indice + 1);
  }

  if (["ArrowLeft", "PageUp"].includes(evento.key)) {
    evento.preventDefault();
    mostrar(indice - 1);
  }

  if (evento.key === "Home") mostrar(0);
  if (evento.key === "End") mostrar(slides.length - 1);
});

mostrar(0);
