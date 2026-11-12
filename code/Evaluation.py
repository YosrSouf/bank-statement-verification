import jiwer


# getting the ground truth text from the file
def load_text(filepath):
    with open(filepath, encoding="utf-8") as f:
        return f.read()


# method to get words extracted it wringly
def save_alignment_errors(ground_truth, text, errors_path, wer, cer):
    output = jiwer.process_words(ground_truth, text)

    reference_words = output.references[0]
    hypothesis_words = output.hypotheses[0]

    with open(errors_path, "w", encoding="utf-8") as f:
        # write WER and CER first
        f.write(f"WER: {wer:.2%}\n")
        f.write(f"CER: {cer:.2%}\n\n")

        for chunk in output.alignments[0]:
            match chunk.type:
                case "substitute":
                    expected = reference_words[chunk.ref_start_idx:chunk.ref_end_idx]
                    extracted = hypothesis_words[chunk.hyp_start_idx:chunk.hyp_end_idx]

                    f.write("SUBSTITUTION\n")
                    f.write("Expected: " + " ".join(expected) + "\n")
                    f.write("Extracted: " + " ".join(extracted) + "\n\n")

                case "delete":
                    expected = reference_words[chunk.ref_start_idx:chunk.ref_end_idx]

                    f.write("DELETION\n")
                    f.write("Missing: " + " ".join(expected) + "\n\n")

                case "insert":
                    extracted = hypothesis_words[chunk.hyp_start_idx:chunk.hyp_end_idx]

                    f.write("INSERTION\n")
                    f.write("Extra: " + " ".join(extracted) + "\n\n")