/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";

const EMOJI_CATEGORIES = [
    {
        label: "📄 Docs",
        emojis: [
            "📄", "📁", "📝", "🗂️", "📎", "📊", "🔑", "🗒️", "📋", "📑",
            "🖊️", "📰", "📚", "📒", "📓", "📔", "📃", "📜", "🗃️", "🗄️",
        ],
    },
    {
        label: "✅ Status",
        emojis: [
            "✅", "❗", "❓", "🔒", "🔓", "⭐", "🏷️", "📌", "🚩", "⚠️",
            "🔔", "💡", "🎯", "🔴", "🟡", "🟢", "⏳", "✔️", "❌", "🔁",
        ],
    },
    {
        label: "👤 People",
        emojis: [
            "👤", "👥", "🧑‍💼", "👨‍💻", "👩‍💻", "🧑‍🏫", "👨‍🔬", "🤝", "👋", "🙋",
            "🧠", "💬", "📣", "📢", "🗣️", "👁️", "🫂", "🤖", "👑", "🏆",
        ],
    },
    {
        label: "🔧 Tools",
        emojis: [
            "🔧", "🛠️", "⚙️", "🔬", "🧪", "💻", "🖥️", "📱", "🌐", "🚀",
            "🗺️", "📡", "🔌", "💡", "🧩", "📐", "📏", "🏗️", "🔍", "🧲",
        ],
    },
];

export class EmojiPicker extends Component {
    static template = "knowledge.EmojiPicker";
    static props = {
        value: { type: String, optional: true },
        onSelect: Function,
        onClose: Function,
    };

    setup() {
        this.categories = EMOJI_CATEGORIES;
        this.state = useState({ activeTab: 0 });
        this.pickerRef = useRef("picker");

        const onKeydown = (ev) => {
            if (ev.key === "Escape") this.props.onClose();
        };
        const onMousedown = (ev) => {
            if (this.pickerRef.el && !this.pickerRef.el.contains(ev.target)) {
                this.props.onClose();
            }
        };

        onMounted(() => {
            document.addEventListener("keydown", onKeydown);
            document.addEventListener("mousedown", onMousedown);
        });
        onWillUnmount(() => {
            document.removeEventListener("keydown", onKeydown);
            document.removeEventListener("mousedown", onMousedown);
        });
    }

    selectEmoji(emoji) {
        this.props.onSelect(emoji);
        this.props.onClose();
    }

    removeIcon() {
        this.props.onSelect("");
        this.props.onClose();
    }

    setTab(index) {
        this.state.activeTab = index;
    }
}
