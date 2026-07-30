(function () {
  "use strict";

  function optionRow(value) {
    const row = document.createElement("div");
    row.className = "input-group input-group-sm mb-2";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "form-control vote-poll-option-input";
    input.maxLength = 255;
    input.value = value || "";

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn-white";
    removeBtn.innerHTML = '<span class="fas fa-xmark"></span>';
    removeBtn.addEventListener("click", () => row.remove());

    row.append(input, removeBtn);
    return row;
  }

  function setupPollDialog() {
    const dialog = document.getElementById("vote-poll-dialog");
    if (!dialog) {
      return;
    }

    const questionInput = document.getElementById("vote-poll-question");
    const typeSingle = document.getElementById("vote-poll-type-single");
    const typeMultiple = document.getElementById("vote-poll-type-multiple");
    const optionsContainer = document.getElementById("vote-poll-options");
    const addOptionBtn = document.getElementById("vote-poll-add-option");
    const insertBtn = document.getElementById("vote-poll-insert");
    const removeBtn = document.getElementById("vote-poll-remove");
    const cancelBtn = document.getElementById("vote-poll-cancel");
    const closeBtn = document.getElementById("vote-poll-close");

    let activeField = null;

    function addOptionRow(value) {
      optionsContainer.append(optionRow(value));
    }

    function notifyFieldChanged() {
      activeField.dispatchEvent(new CustomEvent("change", { bubbles: true }));
    }

    // Exposed on the dialog element itself so <vote-poll-button> instances
    // don't need to know the dialog's internal field/option-row wiring.
    dialog.openForField = function (field) {
      activeField = field;

      let payload = null;
      if (field.value) {
        try {
          payload = JSON.parse(field.value);
        } catch (error) {
          payload = null;
        }
      }

      questionInput.value = payload ? payload.question || "" : "";
      typeMultiple.checked = Boolean(payload) && payload.type === "multiple";
      typeSingle.checked = !typeMultiple.checked;

      optionsContainer.innerHTML = "";
      const options =
        payload && Array.isArray(payload.options) ? payload.options : [];
      for (const option of options) {
        addOptionRow(option);
      }
      while (optionsContainer.children.length < 2) {
        addOptionRow("");
      }

      removeBtn.hidden = !payload;
      dialog.showModal();
    };

    addOptionBtn.addEventListener("click", () => addOptionRow(""));

    insertBtn.addEventListener("click", () => {
      const question = questionInput.value.trim();
      const options = [
        ...optionsContainer.querySelectorAll(".vote-poll-option-input"),
      ]
        .map((input) => input.value.trim())
        .filter((value) => value.length > 0);

      if (!question || options.length < 2) {
        window.alert(dialog.dataset.validationMessage);
        return;
      }

      activeField.value = JSON.stringify({
        question,
        type: typeMultiple.checked ? "multiple" : "single",
        options,
      });
      notifyFieldChanged();
      dialog.close();
    });

    removeBtn.addEventListener("click", () => {
      activeField.value = "";
      notifyFieldChanged();
      dialog.close();
    });

    cancelBtn.addEventListener("click", () => dialog.close());
    closeBtn.addEventListener("click", () => dialog.close());
  }

  setupPollDialog();

  class VotePollButtonElement extends window.MarkdownButtonElement {
    connectedCallback() {
      super.connectedCallback();

      const form = this.closest("form");
      // form.elements.namedItem returns a single element normally, but a
      // RadioNodeList if the form ever has more than one field with this
      // name (no addEventListener) - treat that as "not found" too rather
      // than throwing.
      const field = form ? form.elements.namedItem("poll_data") : null;
      this.hiddenField = field instanceof HTMLInputElement ? field : null;
      const dialog = document.getElementById("vote-poll-dialog");

      // Missing either one means this editor instance has no wired-up poll
      // support (e.g. the quick-reply box, which has no dialog, or editing
      // an existing post) - hide rather than offer a button that can't do
      // anything.
      if (!this.hiddenField || !dialog) {
        this.hidden = true;
        return;
      }

      this.refreshActiveState();
      this.hiddenField.addEventListener("change", () =>
        this.refreshActiveState()
      );

      this.addEventListener("click", (event) => {
        event.preventDefault();
        if (dialog.openForField) {
          dialog.openForField(this.hiddenField);
        }
      });
    }

    refreshActiveState() {
      this.classList.toggle("active", Boolean(this.hiddenField.value));
    }
  }

  if (!window.customElements.get("vote-poll-button")) {
    window.customElements.define("vote-poll-button", VotePollButtonElement);
  }
})();
