<script lang="ts">
  import { onMount } from 'svelte';
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import { getSkuSamples, getSkuDetails, type SkuDetails } from '../lib/api/client';
  import type { PriceSample } from '../lib/api/types';

  interface Props {
    skuCode: string;
  }

  let { skuCode }: Props = $props();

  let samples = $state<PriceSample[]>([]);
  let skuDetails = $state<SkuDetails | null>(null);
  let isLoading = $state(true);
  let error = $state<string | null>(null);
  let chartContainer = $state<HTMLDivElement>(null!);
  let chart: uPlot | null = null;
  let originalScales: { min: number; max: number } | null = null;

  // WeakMaps to store event handlers for cleanup without using `any` type casting
  const dblClickHandlers = new WeakMap<uPlot, () => void>();
  const keyDownHandlers = new WeakMap<uPlot, (e: KeyboardEvent) => void>();

  let stats = $derived.by(() => {
    if (samples.length === 0) {
      return { current: 0, low: 0, high: 0 };
    }

    const prices = samples.map(s => parseFloat(s.product_info.price) * 100);
    return {
      current: prices[prices.length - 1],
      low: Math.min(...prices),
      high: Math.max(...prices),
    };
  });

  function formatPrice(cents: number): string {
    return `$${(cents / 100).toFixed(2)}`;
  }

  function createChart() {
    if (!chartContainer || samples.length === 0) return;

    if (chart) {
      chart.destroy();
    }

    // Reset originalScales so it gets recalculated for the new chart instance
    originalScales = null;

    // Process data to create step chart (horizontal then vertical)
    const processedTimes: number[] = [];
    const processedPrices: number[] = [];

    samples.forEach((sample, i) => {
      const time = new Date(sample.sample_time).getTime() / 1000;
      const price = parseFloat(sample.product_info.price);

      if (i > 0) {
        // Add point at new time with old price (horizontal line)
        processedTimes.push(time);
        processedPrices.push(processedPrices[processedPrices.length - 1]);
      }

      // Add actual point
      processedTimes.push(time);
      processedPrices.push(price);
    });

    const width = Math.min(chartContainer.clientWidth, 800);
    const height = 300;

    const opts: uPlot.Options = {
      width,
      height,
      cursor: {
        show: true,
        drag: { x: true, y: false },
      },
      legend: { show: false },
      axes: [
        {
          stroke: '#6b7280',
          grid: { stroke: '#e5e7eb', width: 1 },
        },
        {
          stroke: '#6b7280',
          grid: { stroke: '#e5e7eb', width: 1 },
          values: (_, vals) => vals.map(v => `$${v.toFixed(2)}`),
        },
      ],
      series: [
        {},
        {
          stroke: '#3b82f6',
          width: 2,
          fill: 'rgba(59, 130, 246, 0.1)',
          points: { show: false },
        },
      ],
      scales: {
        x: { time: true },
        y: { auto: true },
      },
      hooks: {
        ready: [
          (u) => {
            originalScales = {
              min: u.scales.x.min!,
              max: u.scales.x.max!,
            };
          },
        ],
        init: [
          (u) => {
            const resetZoom = () => {
              if (originalScales) {
                u.setScale('x', originalScales);
              }
            };
            const handleDblClick = () => resetZoom();
            const handleKeyDown = (e: KeyboardEvent) => {
              if (e.key === 'r' || e.key === 'R' || e.key === 'Escape') {
                resetZoom();
              }
            };
            u.over.addEventListener('dblclick', handleDblClick);
            u.over.addEventListener('keydown', handleKeyDown);
            // Make the chart focusable for keyboard events
            u.over.setAttribute('tabindex', '0');
            dblClickHandlers.set(u, handleDblClick);
            keyDownHandlers.set(u, handleKeyDown);
          },
        ],
        destroy: [
          (u) => {
            const dblClickHandler = dblClickHandlers.get(u);
            if (dblClickHandler) {
              u.over.removeEventListener('dblclick', dblClickHandler);
              dblClickHandlers.delete(u);
            }
            const keyDownHandler = keyDownHandlers.get(u);
            if (keyDownHandler) {
              u.over.removeEventListener('keydown', keyDownHandler);
              keyDownHandlers.delete(u);
            }
          },
        ],
      },
    };

    chart = new uPlot(opts, [processedTimes, processedPrices], chartContainer);
  }

  function handleBack(event: MouseEvent) {
    event.preventDefault();
    const navigate = (window as any).__navigate;
    if (navigate) {
      navigate('/');
    } else {
      window.location.href = '/';
    }
  }

  function handleResize() {
    createChart();
  }

  onMount(async () => {
    try {
      [samples, skuDetails] = await Promise.all([
        getSkuSamples(skuCode),
        getSkuDetails(skuCode),
      ]);
      setTimeout(createChart, 0);
    } catch (e) {
      error = 'Failed to load price history';
    } finally {
      isLoading = false;
    }

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      if (chart) {
        chart.destroy();
      }
    };
  });
</script>

<div class="min-h-screen bg-gray-50">
  <header class="bg-white shadow-sm">
    <div class="max-w-4xl mx-auto px-4 py-4">
      <a href="/" onclick={handleBack} class="text-blue-600 hover:text-blue-800 text-sm mb-2 inline-block">
        &larr; Back to search
      </a>
      {#if skuDetails}
        <h1 class="text-2xl font-bold text-gray-900">{skuDetails.product_name}</h1>
        <p class="text-sm text-gray-500">SKU: {skuDetails.formatted_code}</p>
      {:else}
        <h1 class="text-2xl font-bold text-gray-900">SKU: {skuCode}</h1>
      {/if}
    </div>
  </header>

  <main class="max-w-4xl mx-auto px-4 py-6">
    {#if isLoading}
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="animate-pulse">
          <div class="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
          <div class="h-64 bg-gray-200 rounded"></div>
        </div>
      </div>
    {:else if error}
      <div class="bg-red-50 border border-red-200 rounded-lg p-4">
        <p class="text-red-800">{error}</p>
      </div>
    {:else}
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Price Statistics</h2>
        <div class="grid grid-cols-3 gap-4">
          <div class="text-center">
            <p class="text-sm text-gray-500">Current</p>
            <p class="text-xl font-bold {stats.current <= stats.low ? 'text-green-600' : ''}">
              {formatPrice(stats.current)}
            </p>
          </div>
          <div class="text-center">
            <p class="text-sm text-gray-500">All-Time Low</p>
            <p class="text-xl font-bold text-green-600">{formatPrice(stats.low)}</p>
          </div>
          <div class="text-center">
            <p class="text-sm text-gray-500">All-Time High</p>
            <p class="text-xl font-bold text-red-600">{formatPrice(stats.high)}</p>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Price History</h2>
        <div bind:this={chartContainer} class="w-full"></div>
        <p class="text-xs text-gray-400 mt-2">Drag horizontally to zoom, double-click or press R/Esc to reset</p>
      </div>
    {/if}
  </main>
</div>
