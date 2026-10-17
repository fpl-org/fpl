import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const concepts = defineCollection({
  loader: glob({
    pattern: "{pass,repr,compose,boundary,labs}/!(index|README).md",
    base: "..",
  }),
  schema: z.object({
    type: z.string(),
    title: z.string(),
    description: z.string(),
    tags: z.array(z.string()).optional(),
    engine: z.string().optional(),
  }),
});

export const collections = { concepts };
