import { createEditor } from './editor/index.js';

const editor = createEditor();
editor.bindEvents();
void editor.commands.init();
