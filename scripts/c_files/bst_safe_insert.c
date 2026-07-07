struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_insert(struct Node* root, int value) {
    struct Node* newNode;
    struct Node* parent;
    struct Node* current;
    int tmp_value;

    // function
	current = root;
	if (current) {

		while (current) {
			parent = current;
			tmp_value = current->data;
			if (value < tmp_value) {
				current = current->left;
			}
			else {
				current = current->right;
			}
		}

		tmp_value = parent->data;
		newNode = malloc(sizeof(struct Node));
		newNode->data = value;
		if (value < tmp_value) {
			parent->left = newNode;
		}
		else {
			parent->right = newNode;
		}
	}
}
