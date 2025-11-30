<script lang="ts">
  interface Props {
    value?: string;
    placeholder?: string;
    oninput?: (value: string) => void;
  }

  let {
    value = $bindable(''),
    placeholder = 'Search products, codes, or SKUs...',
    oninput
  }: Props = $props();

  let timeout: ReturnType<typeof setTimeout>;

  function handleInput(event: Event) {
    const target = event.target as HTMLInputElement;
    value = target.value;

    clearTimeout(timeout);
    timeout = setTimeout(() => {
      oninput?.(value);
    }, 300);
  }

  function handleClear() {
    value = '';
    oninput?.('');
  }
</script>

<div class="relative">
  <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
    <svg class="h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  </div>
  <input
    type="text"
    {value}
    {placeholder}
    oninput={handleInput}
    class="block w-full pl-10 pr-10 py-3 border border-gray-300 rounded-lg text-gray-900 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-lg"
  />
  {#if value}
    <button
      type="button"
      onclick={handleClear}
      class="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600"
      aria-label="Clear search"
    >
      <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
  {/if}
</div>
