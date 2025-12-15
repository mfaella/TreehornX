struct Node {
    int value;
    struct Node *left;
    struct Node *right;
};

void bst_safe_insert(struct Node* root, int value) {
    struct Node* newNode;
    struct Node* parent;
    struct Node* current;
    int temp_value;

    current = root;

    if (current) {
        newNode = malloc(sizeof(struct Node));
        newNode->value = value;

        while (current) {
            parent = current; //5
            temp_value = current->value;
            if (value < temp_value) { //7
                current = current->left;
            }
            else {
                current = current->right;
            }
        }

        temp_value = parent->value; //10
        if (value < temp_value) {
            parent->left = newNode;
        }
        else {
            parent->right = newNode;
        }
    }
}
