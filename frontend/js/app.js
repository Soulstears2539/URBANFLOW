/* Arranque y orquestación de vistas. */
(function () {
  function switchView(view) {
    document.querySelectorAll(".tab").forEach((t) =>
      t.classList.toggle("active", t.dataset.view === view)
    );
    document.getElementById("view-usuario").classList.toggle("active", view === "usuario");
    document.getElementById("view-admin").classList.toggle("active", view === "admin");
    if (view === "usuario" && window.UF.map.instance) {
      setTimeout(() => window.UF.map.instance.invalidateSize(), 100);
    }
    if (view === "admin") window.UF.admin.refreshHealth();
  }

  document.addEventListener("DOMContentLoaded", () => {
    try {
      // Init map and lightweight UI bindings immediately
      window.UF.map.init();
      window.UF.user.bindUI();
      window.UF.admin.bindUI();

      // Defer heavy / network tasks so initial render is faster
      const startDeferred = () => {
        // load traffic map (tiles + small payload)
        window.UF.user.loadTraffic().catch(() => {});

        // start realtime polling when browser is idle or after short delay
        if ('requestIdleCallback' in window) {
          try {
            requestIdleCallback(() => window.UF.user.startRealtime(), { timeout: 2000 });
          } catch (e) {
            setTimeout(() => window.UF.user.startRealtime(), 1200);
          }
        } else {
          setTimeout(() => window.UF.user.startRealtime(), 1200);
        }

        // refresh admin health after map and UI settled
        setTimeout(() => window.UF.admin.refreshHealth(), 1800);
      };

      // Kick deferred work after a brief pause to let the UI paint
      setTimeout(startDeferred, 700);

      document.querySelectorAll(".tab").forEach(tab => {
        tab.addEventListener("click", (e) => {
          e.preventDefault();
          switchView(tab.dataset.view);
        });
      });

      // Mejoras de interactividad
      document.body.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          const resultBlock = document.getElementById("resultado-block");
          if (resultBlock && !resultBlock.hidden) {
            resultBlock.hidden = true;
          }
        }
      });

      // Log inicial
      console.log("✓ UrbanFlow OSM v2.0 mejorado cargado");
    } catch (err) {
      console.error("Error al inicializar:", err);
      window.UF.admin.log(`ERR: ${err.message}`);
    }
  });
})();
