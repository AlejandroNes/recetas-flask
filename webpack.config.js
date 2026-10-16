const path = require('path');
const webpack = require('webpack');

/*
 * Webpack Plugins
 */
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

const ProductionPlugins = [
  // production webpack plugins go here
  new webpack.DefinePlugin({
    "process.env": {
      NODE_ENV: JSON.stringify("production")
    }
  })
]

const isProduction = process.env.NODE_ENV === 'production';
const rootAssetPath = path.join(__dirname, 'assets');

module.exports = {
  // configuration
  context: __dirname,
  entry: {
    main_js: './assets/js/main',
    main_css: [
      path.join(__dirname, 'node_modules', '@fortawesome', 'fontawesome-free', 'css', 'all.css'),
      path.join(__dirname, 'node_modules', 'bootstrap', 'dist', 'css', 'bootstrap.css'),
      path.join(__dirname, 'assets', 'css', 'style.css'),
    ],
  },
  mode: isProduction ? 'production' : 'development',
  output: {
    chunkFilename: "[id].js",
    filename: "[name].bundle.js",
    path: path.join(__dirname, "practica_flask", "static", "build"),
    publicPath: "/static/build/"
  },
  resolve: {
    extensions: [".js", ".jsx", ".css"]
  },
  devtool: isProduction ? false : "eval-source-map",
  plugins: [
    new MiniCssExtractPlugin({ filename: "[name].bundle.css" }),
    new webpack.ProvidePlugin({ $: "jquery", jQuery: "jquery" })
  ].concat(isProduction ? ProductionPlugins : []),
  module: {
    rules: [
      {
        test: /\.less$/,
        use: [
          {
            loader: MiniCssExtractPlugin.loader,
            options: {
            },
          },
          'css-loader!less-loader',
        ],
      },
      {
        test: /\.css$/,
        use: [
          {
            loader: MiniCssExtractPlugin.loader,
            options: {
            },
          },
          'css-loader',
        ],
      },
      { test: /\.html$/, type: 'asset/source' },
      { test: /\.woff(2)?(\?v=[0-9]\.[0-9]\.[0-9])?$/, type: 'asset/resource', mimetype: 'application/font-woff' },
      {
        test: /\.(ttf|eot|svg|png|jpe?g|gif|ico)(\?.*)?$/i,
        type: 'asset/resource',
        generator: {
          filename: '[name][ext]'
        }
      },
      { test: /\.js$/, exclude: /node_modules/, loader: 'babel-loader', options: { presets: ["@babel/preset-env"], cacheDirectory: true } },
    ],
  }
};
