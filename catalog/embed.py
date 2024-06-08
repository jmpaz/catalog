import os
import json
from nomic import embed
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

EMBEDDINGS_PATH = os.path.expanduser("~/.local/share/catalog/embeddings.json")


def vector_search(query, embeddings, locators, top_k=10, device="cpu"):
    query_embedding = embed.text(
        texts=[query],
        model="nomic-embed-text-v1.5",
        task_type="search_document",
        inference_mode="local",
        dimensionality=768,
        device=device,
    )["embeddings"][0]

    similarities = cosine_similarity([query_embedding], embeddings)[0]
    top_indices = np.argsort(similarities)[-top_k:][::-1]

    results = [(locators[i], similarities[i]) for i in top_indices]
    return results


def save_embeddings(embeddings, locators, path=EMBEDDINGS_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"embeddings": embeddings.tolist(), "locators": locators}
    with open(path, "w") as f:
        json.dump(data, f)


def load_embeddings(path=EMBEDDINGS_PATH):
    if os.path.exists(path):
        with open(path, "r") as f:
            data = json.load(f)
            embeddings = np.array(data["embeddings"])
            locators = data["locators"]
            return embeddings, locators
    return np.array([]), []


def prepare_embeddings(library, max_entries=400, device="cpu", path=EMBEDDINGS_PATH):
    """Generate embeddings for object entries."""
    entries_to_embed = []
    for media_object in library.media_objects:
        if hasattr(media_object, "speech_data") and media_object.speech_data:
            entries_to_embed.append(
                (media_object.id, "speech_data", media_object.speech_data[-1])
            )
        elif hasattr(media_object, "transcripts") and media_object.transcripts:
            entries_to_embed.append(
                (media_object.id, "transcripts", media_object.transcripts[-1])
            )

        if len(entries_to_embed) >= max_entries:
            break

    texts = []
    locators = []
    for media_id, entry_type, entry in entries_to_embed:
        if "nodes" in entry:
            for index, node in enumerate(entry["nodes"]):
                content_key = "content" if "content" in node else "text"
                content = node[content_key]
                texts.append(content)
                locator = f"{media_id[:8]}:{entry_type}:{entry['id'][:5]}.nodes:{index}"
                locators.append(locator)

    if texts:
        output = embed.text(
            texts=texts,
            model="nomic-embed-text-v1.5",
            task_type="search_document",
            inference_mode="local",
            dimensionality=768,
            device=device,
        )
        embeddings = np.array(output["embeddings"])
    else:
        embeddings = np.array([])

    save_embeddings(embeddings, locators, path)


def reconcile_embeddings(library, device="cpu", path=EMBEDDINGS_PATH):
    """Update library embeddings with new entries, and remove old ones."""
    existing_embeddings, existing_locators = load_embeddings(path)
    existing_locators_set = set(existing_locators)

    entries_to_embed = []
    for media_object in library.media_objects:
        if hasattr(media_object, "speech_data") and media_object.speech_data:
            entries_to_embed.append(
                (media_object.id, "speech_data", media_object.speech_data[-1])
            )
        elif hasattr(media_object, "transcripts") and media_object.transcripts:
            entries_to_embed.append(
                (media_object.id, "transcripts", media_object.transcripts[-1])
            )

    texts = []
    locators = []
    new_locators_set = set()
    for media_id, entry_type, entry in entries_to_embed:
        if "nodes" in entry:
            for index, node in enumerate(entry["nodes"]):
                content_key = "content" if "content" in node else "text"
                content = node[content_key]
                locator = f"{media_id[:8]}:{entry_type}:{entry['id'][:5]}.nodes:{index}"
                if locator not in existing_locators_set:
                    texts.append(content)
                    locators.append(locator)
                new_locators_set.add(locator)

    # remove redundant entries
    indices_to_keep = [
        i for i, locator in enumerate(existing_locators) if locator in new_locators_set
    ]
    final_embeddings = existing_embeddings[indices_to_keep]
    final_locators = [existing_locators[i] for i in indices_to_keep]

    # append new embeddings
    if texts:
        output = embed.text(
            texts=texts,
            model="nomic-embed-text-v1.5",
            task_type="search_document",
            inference_mode="local",
            dimensionality=768,
            device=device,
        )
        new_embeddings = np.array(output["embeddings"])
        final_embeddings = np.concatenate((final_embeddings, new_embeddings), axis=0)
        final_locators.extend(locators)

    save_embeddings(final_embeddings, final_locators, path)
