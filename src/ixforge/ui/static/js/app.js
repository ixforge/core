document.addEventListener("alpine:init", () => {
  Alpine.store("darkMode", {
    on: localStorage.getItem("darkMode") === "true",
    toggle() {
      this.on = !this.on;
      localStorage.setItem("darkMode", this.on);
      document.documentElement.classList.toggle("dark", this.on);
    },
    init() {
      document.documentElement.classList.toggle("dark", this.on);
    },
  });
});

// HTMX: redirect to login on 401
document.addEventListener("htmx:responseError", (event) => {
  if (event.detail.xhr.status === 401) {
    window.location.href = "/login";
  }
});
