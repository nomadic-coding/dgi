/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { SelectionField, selectionField } from "@web/views/fields/selection/selection_field";

export class HkaFilteredSelectionField extends SelectionField {
    static props = {
        ...SelectionField.props,
        allowedField: { type: String, optional: true },
    };

    get options() {
        const options = super.options;
        const fieldName = this.props.allowedField;
        if (!fieldName) {
            return options;
        }
        const raw = this.props.record.data[fieldName] || "";
        if (!raw) {
            return options;
        }
        const allowed = new Set(raw.split(",").filter(Boolean));
        return options.filter((option) => allowed.has(option[0]));
    }

    get string() {
        if (this.type !== "selection") {
            return super.string;
        }
        const value = this.props.record.data[this.props.name];
        if (value === false) {
            return "";
        }
        const match = this.options.find((option) => option[0] === value);
        if (match) {
            return match[1];
        }
        const all = this.props.record.fields[this.props.name].selection || [];
        const fallback = all.find((option) => option[0] === value);
        return fallback ? fallback[1] : "";
    }
}

export const hkaFilteredSelectionField = {
    ...selectionField,
    component: HkaFilteredSelectionField,
    displayName: _t("HKA Filtered Selection"),
    extractProps(fieldInfo, dynamicInfo) {
        const props = selectionField.extractProps(fieldInfo, dynamicInfo);
        props.allowedField = (fieldInfo.options || {}).allowed_field;
        return props;
    },
};

registry.category("fields").add("hka_filtered_selection", hkaFilteredSelectionField);
