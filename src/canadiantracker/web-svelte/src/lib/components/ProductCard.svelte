<script lang="ts">
  import type { SearchResult, Deal } from '../api/types';
  import Sparkline from './Sparkline.svelte';

  interface Props {
    item: SearchResult | Deal;
  }

  let { item }: Props = $props();

  let isDeal = $derived('discount_percent' in item);
  let isAtLow = $derived(item.stats.current <= item.stats.all_time_low);

  function formatPrice(cents: number): string {
    return `$${(cents / 100).toFixed(2)}`;
  }

  function handleClick(event: MouseEvent) {
    event.preventDefault();
    const navigate = (window as any).__navigate;
    if (navigate) {
      navigate(`/skus/${item.sku_code}`);
    } else {
      window.location.href = `/skus/${item.sku_code}`;
    }
  }
</script>

<a
  href="/skus/{item.sku_code}"
  onclick={handleClick}
  class="block bg-white rounded-lg shadow-sm border border-gray-200 p-4 hover:shadow-md transition-shadow"
>
  <div class="flex flex-col sm:flex-row sm:items-center gap-4">
    <div class="flex-1 min-w-0">
      <h3 class="text-sm font-medium text-gray-900 truncate">{item.product_name}</h3>
      <p class="text-xs text-gray-500 mt-1">
        SKU: {item.sku_formatted_code || item.sku_code}
      </p>
    </div>

    <div class="flex items-center gap-4">
      {#if item.stats.samples.length > 0}
        <Sparkline
          data={item.stats.samples}
          currentPrice={item.stats.current}
          allTimeLow={item.stats.all_time_low}
          width={120}
          height={36}
        />
      {/if}

      <div class="text-right min-w-[80px]">
        <div class="text-lg font-semibold {isAtLow ? 'text-green-600' : 'text-gray-900'}">
          {formatPrice(item.stats.current)}
        </div>
        {#if isAtLow}
          <span class="inline-block px-1.5 py-0.5 text-xs font-medium bg-green-100 text-green-800 rounded">
            ALL-TIME LOW
          </span>
        {:else if isDeal}
          <span class="text-xs text-gray-500">
            Low: {formatPrice(item.stats.all_time_low)}
          </span>
        {/if}
      </div>
    </div>
  </div>
</a>
