// typescript-eslint does not support TypeScript 7 yet (typescript-eslint#10940).
// Give the typescript-eslint packages their own TypeScript 6 so `pnpm lint` works
// while the project itself keeps typechecking with TypeScript 7.
function readPackage(pkg) {
  if (pkg.name === "typescript-eslint" || pkg.name.startsWith("@typescript-eslint/")) {
    if (pkg.peerDependencies) delete pkg.peerDependencies.typescript;
    pkg.dependencies = { ...pkg.dependencies, typescript: "npm:typescript@6.0.3" };
  }
  return pkg;
}
module.exports = { hooks: { readPackage } };
