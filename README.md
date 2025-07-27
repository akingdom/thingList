# thingList
Categorised lists of things for AI image and media generation, built as single javascript file

This clones and transforms lists from [Lists for Prompts](https://github.com/ai-prompts/prompt-lists).

*Examples*

`things('acorn woodpecker')` returns:
```javascript
{
    "title": "All birds",
    "category": "animal"
}
```

**ThingIndex.js**

```javascript
// Auto-generated
export const thingCategories = [
  {
    "title": "All birds",
    "category": "animal"
  },
  {
    "title": "Deep sea animals",
    "category": "animal"
  },
  {
    "title": "Dinosaurs",
    "category": "animal"
  },
  {
    "title": "Dog breeds",
    "category": "animal"
  },
  ...
];
export const thingKV = {
  "abert's towhee": 0,
  "acadian flycatcher": 0,
  "acorn woodpecker": 0,
  "alder flycatcher": 0,
  "aleutian tern": 0,
  "allen's hummingbird": 0,
  "altamira oriole": 0,
  "american avocet": 0,
  ...
  "zooms": 234
};
export function things(name) {
  const id = thingKV[name.toLowerCase()];
  return id !== undefined ? thingCategories[id] : null;
}
export default { thingCategories, thingKV, things };
```

