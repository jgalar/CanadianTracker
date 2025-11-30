export interface Product {
  name: string;
  code: string;
}

export interface Sku {
  code: string;
  formatted_code: string;
}

export interface PriceSample {
  sample_time: string;
  product_info: {
    price: string;
    in_promo: boolean;
  };
}

export interface PriceStats {
  current: number;
  all_time_low: number;
  all_time_high: number;
  samples: Array<{ time: number; price: number }>;
}

export interface SearchResult {
  product_name: string;
  product_code: string;
  sku_code: string;
  sku_formatted_code: string;
  stats: PriceStats;
}

export interface Deal extends SearchResult {
  discount_percent: number;
}
