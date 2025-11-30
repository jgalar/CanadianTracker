<script lang="ts">
  import { onMount } from 'svelte';
  import SearchBox from '../lib/components/SearchBox.svelte';
  import ProductCard from '../lib/components/ProductCard.svelte';
  import { searchProducts, getDeals } from '../lib/api/client';
  import type { SearchResult, Deal } from '../lib/api/types';

  let searchQuery = $state('');
  let searchResults = $state<SearchResult[]>([]);
  let deals = $state<Deal[]>([]);
  let isSearching = $state(false);
  let isLoadingDeals = $state(true);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      deals = await getDeals(20);
    } catch (e) {
      console.error('Failed to load deals:', e);
    } finally {
      isLoadingDeals = false;
    }
  });

  async function handleSearch(query: string) {
    searchQuery = query;

    if (!searchQuery.trim()) {
      searchResults = [];
      return;
    }

    isSearching = true;
    error = null;

    try {
      searchResults = await searchProducts(searchQuery);
    } catch (e) {
      error = 'Search failed. Please try again.';
      searchResults = [];
    } finally {
      isSearching = false;
    }
  }

  let showingSearch = $derived(searchQuery.trim().length > 0);
</script>

<div class="min-h-screen bg-gray-50">
  <header class="bg-white shadow-sm sticky top-0 z-10">
    <div class="max-w-4xl mx-auto px-4 py-4">
      <h1 class="text-2xl font-bold text-gray-900 mb-4">Canadian Tracker</h1>
      <SearchBox oninput={handleSearch} />
    </div>
  </header>

  <main class="max-w-4xl mx-auto px-4 py-6">
    {#if error}
      <div class="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
        <p class="text-red-800">{error}</p>
      </div>
    {/if}

    {#if showingSearch}
      <section>
        <h2 class="text-lg font-semibold text-gray-900 mb-4">
          {#if isSearching}
            Searching...
          {:else}
            Search Results ({searchResults.length})
          {/if}
        </h2>

        {#if !isSearching && searchResults.length === 0}
          <p class="text-gray-500">No results found for "{searchQuery}"</p>
        {:else}
          <div class="space-y-3">
            {#each searchResults as result (result.sku_code)}
              <ProductCard item={result} />
            {/each}
          </div>
        {/if}
      </section>
    {:else}
      <section>
        <h2 class="text-lg font-semibold text-gray-900 mb-4">
          Best Deals
          <span class="text-sm font-normal text-gray-500">(lowest prices vs. all-time high)</span>
        </h2>

        {#if isLoadingDeals}
          <div class="space-y-3">
            {#each Array(5) as _}
              <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 animate-pulse">
                <div class="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
                <div class="h-3 bg-gray-200 rounded w-1/4"></div>
              </div>
            {/each}
          </div>
        {:else if deals.length === 0}
          <p class="text-gray-500">No deals available at the moment.</p>
        {:else}
          <div class="space-y-3">
            {#each deals as deal (deal.sku_code)}
              <ProductCard item={deal} />
            {/each}
          </div>
        {/if}
      </section>
    {/if}
  </main>
</div>
