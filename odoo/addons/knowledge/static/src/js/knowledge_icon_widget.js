/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { EmojiPicker } from "./emoji_picker";

class KnowledgeIconWidget extends Component {
    static template = "knowledge.IconWidget";
    static props = { ...standardFieldProps };
    static components = { EmojiPicker };

    setup() {
        this.state = useState({ open: false });
    }

    get currentValue() {
        return this.props.record.data[this.props.name] || "";
    }

    togglePicker() {
        this.state.open = !this.state.open;
    }

    closePicker() {
        this.state.open = false;
    }

    async onPickEmoji(emoji) {
        await this.props.record.update({ [this.props.name]: emoji });
        this.closePicker();
    }
}

registry.category("fields").add("knowledge_icon_picker", {
    component: KnowledgeIconWidget,
    extractProps: () => ({}),
});
