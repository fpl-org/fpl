-- The sidebar title is the address in the filename plus the note's own
-- name. A first heading that only repeats that name is dropped. The
-- Marimo setup cell is the notebook's, not the essay's. A link that
-- names a sibling note opens that chapter.

local function address(path)
  local stem = path:match("([^/]+)%.[^%.]+$") or ""
  local addr, slug = stem:match("^(%d%d%.%d%d%.%d%d%.%d%d)%-(.+)$")
  if addr then
    return addr, slug
  end
  addr, slug = stem:match("^(%d%d%.%d%d%.%d%d)%-(.+)$")
  if addr then
    return addr, slug
  end
  return stem:match("^(%d%d%.%d%d)%-(.+)$")
end

local function nice(slug)
  return (slug:gsub("-", " "):gsub("(%a)([%w']*)", function(a, rest)
    return a:upper() .. rest
  end))
end

function Pandoc(doc)
  local file = ""
  if quarto.doc ~= nil and quarto.doc.input_file ~= nil then
    file = quarto.doc.input_file
  else
    file = PANDOC_STATE.input_file or ""
  end
  local addr, slug = address(file)
  local bare = pandoc.utils.stringify(doc.meta.title or "")
  if addr then
    if bare == "" and slug then
      bare = nice(slug)
    end
    if bare:sub(1, #addr) ~= addr then
      bare = addr .. " " .. bare
      doc.meta.title = pandoc.MetaInlines({ pandoc.Str(bare) })
    end
  end
  local blocks = {}
  local dropped = false
  for _, block in ipairs(doc.blocks) do
    if not dropped and block.t == "Header" and block.level == 1 then
      local text = pandoc.utils.stringify(block.content)
      if text == bare or (addr and text == (addr .. " " .. bare)) then
        dropped = true
      else
        table.insert(blocks, block)
      end
    elseif block.t == "CodeBlock" and block.attributes["name"] == "setup" then
      -- the notebook preamble, not part of the reading
    else
      table.insert(blocks, block)
    end
  end
  doc.blocks = blocks
  return doc
end

function Link(link)
  if FORMAT == "html" then
    link.target = link.target:gsub("%.md$", ".html")
  end
  return link
end
