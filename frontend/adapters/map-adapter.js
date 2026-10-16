(() => {
  const fallback = window.lpMap;
  const mode = new URLSearchParams(window.location.search).get("map") || "maplibre";
  const adapter = mode === "maplibre" && window.lpMapLibreAdapterFactory
    ? window.lpMapLibreAdapterFactory.create({ fallbackController: fallback })
    : null;
  if (!adapter) return;
  window.lpMap = {
    state: adapter.state,
    render: (context) => adapter.render(context),
    setZoom: (value, context) => adapter.setZoom(value, context),
    reset: (context) => adapter.reset(context),
    toggleDem: (context) => adapter.toggleDem(context),
    setFilters: (filters, context) => adapter.setFilters(filters, context),
    adapter,
  };
})();
