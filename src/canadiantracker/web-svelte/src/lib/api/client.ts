import type { SearchResult, Deal, PriceSample, Product, Sku } from './types';

const API_BASE = '/api';

export async function searchProducts(query: string): Promise<SearchResult[]> {
  if (!query.trim()) {
    return [];
  }
  const response = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
  if (!response.ok) {
    throw new Error('Search failed');
  }
  return response.json();
}

export async function getDeals(limit: number = 20): Promise<Deal[]> {
  const response = await fetch(`${API_BASE}/deals?limit=${limit}`);
  if (!response.ok) {
    throw new Error('Failed to fetch deals');
  }
  return response.json();
}

export async function getProducts(): Promise<Product[]> {
  const response = await fetch(`${API_BASE}/products`);
  if (!response.ok) {
    throw new Error('Failed to fetch products');
  }
  return response.json();
}

export async function getProduct(code: string): Promise<{ skus: Sku[] }> {
  const response = await fetch(`${API_BASE}/products/${code}`);
  if (!response.ok) {
    throw new Error('Failed to fetch product');
  }
  return response.json();
}

export async function getSkuSamples(skuCode: string): Promise<PriceSample[]> {
  const response = await fetch(`${API_BASE}/skus/${skuCode}/samples`);
  if (!response.ok) {
    throw new Error('Failed to fetch samples');
  }
  return response.json();
}

export interface SkuDetails {
  code: string;
  formatted_code: string;
  product_name: string;
  product_code: string;
}

export async function getSkuDetails(skuCode: string): Promise<SkuDetails> {
  const response = await fetch(`${API_BASE}/skus/${skuCode}`);
  if (!response.ok) {
    throw new Error('Failed to fetch SKU details');
  }
  return response.json();
}
