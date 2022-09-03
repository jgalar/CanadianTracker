const path = require('path');
const MiniCssExtractPlugin = require("mini-css-extract-plugin")

module.exports = {
  entry:
  {
    index: './src/index.ts',
    sku: './src/sku.ts',
    style: [
      './node_modules/bootstrap/dist/css/bootstrap.min.css',
      './node_modules/datatables.net-bs5/css/dataTables.bootstrap5.min.css',
    ],
  },
  module: {
    rules: [
      {
        test: /\.ts$/,
        use: 'ts-loader',
        exclude: /node_modules/,
      },
      {
        test: /\.css$/,
        use: [
          MiniCssExtractPlugin.loader,
          'css-loader'
        ]
      }
    ],
  },
  resolve: {
    extensions: ['.ts', '.js', '.css'],
  },
  output: {
    filename: '[name].js',
    path: path.resolve(__dirname, 'dist'),
  },
  plugins: [
    new MiniCssExtractPlugin(),
  ],
};
