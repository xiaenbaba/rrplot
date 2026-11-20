import { createEditorState } from './state.js';
import { createUiController } from './ui.js';
import { createSessionController } from './session.js';
import { createInspectorController } from './inspector.js';
import { createKeyboardController } from './keyboard.js';
import { createSelectionController } from './selection.js';
import { createConnectionsController } from './connections.js';
import { createViewportController } from './viewport.js';
import { createFilesController } from './files.js';
import { createCanvasController } from './canvas.js';
import { createPointerController } from './pointer.js';
import { createCoordinatesController } from './coordinates.js';
import { createExportController } from './export.js';
import { createSidebarController } from './sidebar.js';
import { createEventsController } from './events.js';
import { createStylesController } from './styles.js';
import { createStartupController } from './startup.js';
import { createRoutingController } from './routing.js';

/** Wire one editor instance. Factories never import each other.
 * The shared command table resolves cross-controller calls without import cycles;
 * mutable document/session data lives exclusively in state.
 */
export function createEditor() {
  const state = createEditorState();
  const commands = {};
  Object.assign(commands, createUiController(state, commands));
  Object.assign(commands, createSessionController(state, commands));
  Object.assign(commands, createInspectorController(state, commands));
  Object.assign(commands, createKeyboardController(state, commands));
  Object.assign(commands, createSelectionController(state, commands));
  Object.assign(commands, createConnectionsController(state, commands));
  Object.assign(commands, createViewportController(state, commands));
  Object.assign(commands, createFilesController(state, commands));
  Object.assign(commands, createCanvasController(state, commands));
  Object.assign(commands, createPointerController(state, commands));
  Object.assign(commands, createCoordinatesController(state, commands));
  Object.assign(commands, createExportController(state, commands));
  Object.assign(commands, createSidebarController(state, commands));
  Object.assign(commands, createEventsController(state, commands));
  Object.assign(commands, createStylesController(state, commands));
  Object.assign(commands, createStartupController(state, commands));
  Object.assign(commands, createRoutingController(state, commands));
  let bound = false;
  function bindEvents() {
    if (bound) return;
    bound = true;
    state.singleKeyShortcuts = commands.readShortcutPreference();
    commands.bindSidebarEvents();
    commands.bindPageEvents();
    commands.bindSelectionEvents();
    commands.bindCoordinatesEvents();
    commands.bindExportEvents();
    commands.bindFilesEvents();
    commands.bindPointerEvents();
    commands.bindStylesEvents();
    commands.bindKeyboardEvents();
    commands.bindBenchmarkEvents();
  }
  return { state, commands, bindEvents };
}
