import plugin from "eslint-plugin-tailwindcss";
console.log(JSON.stringify(plugin, null, 2));
try {
  console.log("Keys:", Object.keys(plugin));
  console.log("Configs:", plugin.configs ? Object.keys(plugin.configs) : "None");
} catch (e) {
  console.error(e);
}
