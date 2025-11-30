<script lang="ts">
  import { onMount } from 'svelte';
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';

  interface Props {
    data: Array<{ time: number; price: number }>;
    width?: number;
    height?: number;
    currentPrice?: number | null;
    allTimeLow?: number | null;
  }

  let { data, width = 150, height = 40, currentPrice = null, allTimeLow = null }: Props = $props();

  let container: HTMLDivElement;
  let chart: uPlot | null = null;

  function createChart() {
    if (!container || data.length === 0) return;

    if (chart) {
      chart.destroy();
    }

    // Process data to create step chart (horizontal then vertical)
    const processedTimes: number[] = [];
    const processedPrices: number[] = [];

    if (data.length === 1) {
      // Single data point: create a horizontal line
      const point = data[0];
      const timeSpan = 60 * 60 * 24 * 7; // 1 week in seconds
      processedTimes.push(point.time - timeSpan);
      processedPrices.push(point.price);
      processedTimes.push(point.time);
      processedPrices.push(point.price);
    } else {
      data.forEach((point, i) => {
        if (i > 0) {
          // Add point at new time with old price (horizontal line)
          processedTimes.push(point.time);
          processedPrices.push(processedPrices[processedPrices.length - 1]);
        }
        // Add actual point
        processedTimes.push(point.time);
        processedPrices.push(point.price);
      });
    }

    const isAtLow = currentPrice !== null && allTimeLow !== null && currentPrice <= allTimeLow;
    const lineColor = isAtLow ? '#22c55e' : '#6b7280';

    const opts: uPlot.Options = {
      width,
      height,
      cursor: { show: false },
      legend: { show: false },
      axes: [
        { show: false },
        { show: false },
      ],
      series: [
        {},
        {
          stroke: lineColor,
          width: 1.5,
          fill: isAtLow ? 'rgba(34, 197, 94, 0.1)' : 'rgba(107, 114, 128, 0.1)',
        },
      ],
      scales: {
        x: { time: false },
        y: { auto: true },
      },
    };

    chart = new uPlot(opts, [processedTimes, processedPrices], container);
  }

  onMount(() => {
    createChart();
    return () => {
      if (chart) {
        chart.destroy();
      }
    };
  });

  $effect(() => {
    // Re-create chart when data changes
    data;
    if (container) {
      createChart();
    }
  });
</script>

<div bind:this={container} class="sparkline"></div>

<style>
  .sparkline {
    display: inline-block;
  }
  .sparkline :global(.u-wrap) {
    display: block !important;
  }
</style>
