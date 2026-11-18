/** Separate output allows isolated browser tests beside the development preview. */
const nextConfig = {
  distDir: process.env.NEXT_OUTPUT_DIR || ".next",
  devIndicators: false,
};
export default nextConfig;
