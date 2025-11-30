<script lang="ts">
  import Home from './routes/Home.svelte';
  import SkuDetail from './routes/SkuDetail.svelte';

  // Simple hash-based or path-based routing
  let currentPath = $state(window.location.pathname);

  // Listen for popstate (back/forward)
  $effect(() => {
    const handlePopState = () => {
      currentPath = window.location.pathname;
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  });

  // Navigate function for links
  function navigate(path: string) {
    window.history.pushState({}, '', path);
    currentPath = path;
  }

  // Make navigate available globally
  if (typeof window !== 'undefined') {
    (window as any).__navigate = navigate;
  }

  // Parse route
  let route = $derived.by(() => {
    const skuMatch = currentPath.match(/^\/skus\/(.+)$/);
    if (skuMatch) {
      return { type: 'sku', skuCode: skuMatch[1] };
    }
    return { type: 'home' };
  });
</script>

{#if route.type === 'sku'}
  <SkuDetail skuCode={route.skuCode} />
{:else}
  <Home />
{/if}
