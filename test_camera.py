from deepface import DeepFace

if __name__ == "__main__":
    DeepFace.stream(
        db_path="registered_faces",
        model_name="ArcFace",
        detector_backend="opencv",
        enable_face_analysis=False
    )