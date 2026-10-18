import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const concepts = defineCollection({
  loader: glob({
    pattern: "{01.01-boundary,01.02-pass,01.03-repr,01.04-compose,01.05-labs,01.06-nagini}/!(index).md",
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
