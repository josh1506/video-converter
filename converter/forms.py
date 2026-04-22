import re

from django import forms


SUPPORTED_OUTPUT_FORMATS = (
    "mp4",
    "mkv",
    "mov",
    "avi",
    "webm",
    "flv",
    "wmv",
    "m4v",
    "mpeg",
    "mpg",
    "3gp",
    "ts",
)


class ConversionRequestForm(forms.Form):
    output_format = forms.CharField(max_length=10, required=True)

    def clean_output_format(self) -> str:
        output_format = self.cleaned_data["output_format"].strip().lower().lstrip(".")
        if not re.fullmatch(r"[a-z0-9]{2,10}", output_format):
            raise forms.ValidationError(
                "Use only letters and numbers for the output format."
            )
        return output_format
