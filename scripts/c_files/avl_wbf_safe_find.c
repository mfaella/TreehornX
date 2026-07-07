#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>

enum BF {
    HIGH_LEFT, LOW_LEFT, NEUTRAL, LOW_RIGHT, HIGH_RIGHT
};

struct Node {
    int data;
    enum BF bf;
    struct Node *left;
    struct Node *right;
};

void bst_safe_find(struct Node* root, int key) {
    struct Node* current;
    struct Node* result;
    struct Node *null;
    int value;
    current = root;

    while (current) {
        value = current->data;
        if (value == key) {
            result = current;
            current = null;
        } else if (key < value) {
            current = current->left;
        } else {
            current = current->right;
        }
    }
}
